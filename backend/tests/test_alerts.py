import asyncio
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.models.monitoring import ReadingInput
from conftest import database_command, frame

API = "/api/v1"


def test_repeat_after_recovery_and_backup_handoff(client: TestClient) -> None:
    patient = client.get(f"{API}/dashboard").json()["patients"][0]["patient"]
    primary = {"X-Demo-Caregiver-Id": patient["primary_caregiver_id"]}
    backup = {"X-Demo-Caregiver-Id": patient["backup_caregiver_id"]}
    assert client.post(f"{API}/readings", json=frame(1) | {"spo2_pct": 88}).status_code == 201
    [alert] = client.get(f"{API}/alerts").json()["items"]
    detail = f"{API}/alerts/{alert['id']}"
    path = detail + "/acknowledge"
    assert client.post(path, headers=primary, json={"command_id": str(uuid4())}).status_code == 200
    for sequence, oxygen in [(2, 98), (3, 93), (4, 88)]:
        assert client.post(f"{API}/readings", json=frame(sequence) | {"spo2_pct": oxygen}).status_code == 201
    assert client.get(detail).json()["status"] == "open"
    remaining = asyncio.run(database_command("SELECT extract(epoch FROM escalation_due_at-now()) FROM alerts"))
    assert 0 < remaining <= 30
    asyncio.run(database_command("UPDATE alerts SET escalation_due_at=now()"))
    deadline = time.monotonic() + 8
    while client.get(detail).json()["assignee_id"] != patient["backup_caregiver_id"]:
        assert time.monotonic() < deadline
        time.sleep(0.1)
    assert client.post(path, headers=primary, json={"command_id": str(uuid4())}).status_code == 403
    assert client.post(path, headers=backup, json={"command_id": str(uuid4())}).status_code == 200
    events = client.get(detail).json()["events"]
    assert [e["event_type"] for e in events] == ["opened","acknowledged","reopened","updated","escalated","acknowledged"]
    assert asyncio.run(database_command("SELECT escalation_due_at FROM alerts")) is None


def test_explained_episode_and_acknowledgement(client: TestClient) -> None:
    dashboard = client.get(f"{API}/dashboard").json()
    patient = dashboard["patients"][0]["patient"]
    primary = {"X-Demo-Caregiver-Id": patient["primary_caregiver_id"]}
    backup = {"X-Demo-Caregiver-Id": patient["backup_caregiver_id"]}
    first = frame(1) | {"spo2_pct": 93}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post(f"{API}/readings", json=first), range(4)))
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 201]
    assert len({r.json()["assessment_id"] for r in responses}) == 1
    original = responses[0].json()["assessment_id"]
    [opening] = client.get(f"{API}/alerts", params={"patient_id": patient["id"]}).json()["items"]
    assert opening["latest_assessment"]["id"] == original
    assert (opening["status"], opening["revision"], opening["peak_priority"]) == ("open", 1, "watch")
    assert opening["assignee_id"] == patient["primary_caregiver_id"]

    second = frame(2) | {"spo2_pct": 88, "heart_rate_bpm": 115, "temperature_c": None}
    receipt = client.post(f"{API}/readings", json=second)
    assert receipt.status_code == 201
    [alert] = client.get(f"{API}/dashboard").json()["active_alerts"]
    assert alert["id"] == opening["id"]
    assert alert["original_assessment"]["id"] == original
    assessment = alert["latest_assessment"]
    assert assessment["id"] == receipt.json()["assessment_id"]
    assert assessment["reading_id"] == second["reading_id"]
    assert (assessment["concern"], assessment["data_quality"], assessment["scope"]) == ("high", "incomplete", "current")
    assert assessment["rule_version"] == "demo-context-v1"
    hr, oxygen = assessment["findings"]
    assert (hr["priority"], hr["value"], hr["unit"], hr["condition"]) == ("watch", 115, "bpm", "> 110")
    assert (oxygen["rule_id"], oxygen["value"], oxygen["unit"], oxygen["condition"]) == ("spo2_pct.low.high", 88, "%", "< 90")
    assert all(f["reading_id"] == second["reading_id"] and
               datetime.fromisoformat(f["observed_at"]) == datetime.fromisoformat(second["observed_at"])
               for f in assessment["findings"])
    assert client.get(f"{API}/patients/{patient['id']}").json()["current_assessment"] == assessment

    detail = f"{API}/alerts/{alert['id']}"
    path = detail + "/acknowledge"
    command = {"command_id": str(uuid4())}
    assert client.post(path, json=command, headers=backup).status_code == 403
    assert client.post(path, json=command).status_code == 422
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: client.post(path, json=command, headers=primary), range(3)))
    assert all(r.status_code == 200 for r in results)
    saved = results[0].json()
    assert all(r.json() == saved for r in results)
    assert (saved["status"], saved["revision"], saved["peak_priority"]) == ("acknowledged", 3, "high")
    assert saved["acknowledged_by"] == saved["assignee_id"]
    assert client.post(path, json={"command_id": str(uuid4())}, headers=primary).status_code == 409
    events = client.get(detail).json()["events"]
    assert [e["event_type"] for e in events] == ["opened", "updated", "acknowledged"]
    assert [e["assessment_id"] for e in events[:2]] == [original, assessment["id"]]
    assert events[-1]["occurred_at"] == saved["acknowledged_at"]
    assert events[-1]["caregiver_id"] == saved["assignee_id"]

    third = frame(3) | {"spo2_pct": 92}
    assert client.post(f"{API}/readings", json=third).status_code == 201
    refreshed = client.get(detail).json()
    assert (refreshed["status"], refreshed["peak_priority"], refreshed["revision"]) == ("acknowledged", "high", 4)
    assert refreshed["latest_assessment"]["concern"] == "watch"
    dashboard = client.get(f"{API}/dashboard").json()
    assert dashboard["patients"][0]["current_assessment"] == refreshed["latest_assessment"]
    assert dashboard["active_alerts"][0]["peak_priority"] == "high"

    other = frame(1) | {"device_id": dashboard["patients"][1]["patient"]["device_id"], "heart_rate_bpm": 144}
    assert client.post(f"{API}/readings", json=other).status_code == 201
    page = client.get(f"{API}/alerts", params={"limit": 1}).json()
    [other_alert] = page["items"]
    assert client.get(f"{API}/alerts", params={"cursor": page["next_cursor"]}).json()["items"][0]["id"] == alert["id"]
    conflict = client.post(f"{API}/alerts/{other_alert['id']}/acknowledge", json=command, headers=primary)
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "command_conflict"
    assert client.get(f"{API}/alerts/{other_alert['id']}").json()["status"] == "open"


def test_open_risk_retains_strongest_assessment_until_acknowledgement(client: TestClient) -> None:
    dashboard = client.get(f"{API}/dashboard").json()
    assert [actor["display_name"] for actor in dashboard["caregivers"]] == ["Primary caregiver", "Backup caregiver"]
    primary = dashboard["patients"][0]["patient"]["primary_caregiver_id"]
    for sequence, spo2, heart_rate in [(1, 93, 73), (2, 93, 115), (3, 93, 73), (4, 99, 73)]:
        client.post(f"{API}/readings", json=frame(sequence) | {"spo2_pct": spo2, "heart_rate_bpm": heart_rate}).raise_for_status()
    dashboard = client.get(f"{API}/dashboard").json()
    [alert] = dashboard["active_alerts"]
    assert dashboard["patients"][0]["current_assessment"]["concern"] == "none"
    assert alert["latest_assessment"]["concern"] == "watch"
    assert {f["metric"] for f in alert["pending_risk_assessment"]["findings"]} == {"spo2_pct", "heart_rate_bpm"}
    response = client.post(f"{API}/alerts/{alert['id']}/acknowledge", json={"command_id": str(uuid4())},
                           headers={"X-Demo-Caregiver-Id": primary})
    assert response.status_code == 200 and response.json()["pending_risk_assessment"] is None
    client.post(f"{API}/readings", json=frame(5) | {"spo2_pct": 93}).raise_for_status()
    [reopened] = client.get(f"{API}/dashboard").json()["active_alerts"]
    assert reopened["status"] == "open"
    assert reopened["pending_risk_assessment"]["id"] == reopened["latest_assessment"]["id"]


def test_missing_and_historical_readings(client: TestClient) -> None:
    patient = client.get(f"{API}/dashboard").json()["patients"][2]["patient"]
    path = f"{API}/patients/{patient['id']}"
    base = frame(11) | {"device_id": patient["device_id"]}
    missing = base | {k: None for k in ("heart_rate_bpm", "spo2_pct", "systolic_mmhg", "diastolic_mmhg", "temperature_c")}
    assert client.post(f"{API}/readings", json=missing).status_code == 201
    assessment = client.get(path).json()["current_assessment"]
    assert (assessment["concern"], assessment["data_quality"], assessment["findings"]) == (None, "incomplete", [])
    old = frame(12) | {"device_id": patient["device_id"], "spo2_pct": 80,
                       "observed_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat()}
    assert client.post(f"{API}/readings", json=old).status_code == 201
    assert client.get(path).json()["current_assessment"] == assessment
    [review] = client.get(f"{API}/alerts", params={"patient_id": patient["id"]}).json()["items"]
    assert review["kind"] == "delayed_review" and review["latest_assessment"]["scope"] == "historical"


def test_event_write_failure_rolls_back_all_effects(client: TestClient) -> None:
    patient = client.get(f"{API}/dashboard").json()["patients"][2]["patient"]
    path = f"{API}/patients/{patient['id']}"
    before = client.get(path).json()
    payload = frame(100) | {"device_id": patient["device_id"], "spo2_pct": 88}
    # A real constraint rejects the final audit insert after the other writes have succeeded.
    asyncio.run(database_command("ALTER TABLE alert_events ADD CONSTRAINT reject_test_event CHECK (false) NOT VALID"))
    try:
        failed = client.post(f"{API}/readings", json=payload)
        assert failed.status_code == 503
        assert client.get(path).json() == before
        assert all(r["reading_id"] != payload["reading_id"] for r in client.get(path + "/readings").json()["items"])
        assert client.get(f"{API}/alerts", params={"patient_id": patient["id"]}).json()["items"] == []
        assert asyncio.run(database_command("SELECT count(*) FROM assessments WHERE reading_id = :id",
                                            {"id": payload["reading_id"]})) == 0
    finally:
        asyncio.run(database_command("ALTER TABLE alert_events DROP CONSTRAINT reject_test_event"))
    assert client.post(f"{API}/readings", json=payload).status_code == 201
    [alert] = client.get(f"{API}/alerts", params={"patient_id": patient["id"]}).json()["items"]
    assert alert["revision"] == 1


def test_upgrade_preserves_m1_receipt(client: TestClient) -> None:
    config = Config("alembic.ini")
    command.downgrade(config, "0001_environment")
    command.upgrade(config, "0002_monitoring")
    reading = ReadingInput.model_validate(frame() | {"spo2_pct": 88})
    patient_id = "20000000-0000-0000-0000-000000000001"
    values = reading.model_dump() | {
        "patient_id": patient_id, "hash": hashlib.sha256(reading.model_dump_json().encode()).hexdigest(),
    }
    received = asyncio.run(database_command("""
        INSERT INTO readings (id, device_id, patient_id, sequence, observed_at, heart_rate_bpm,
                              spo2_pct, systolic_mmhg, diastolic_mmhg, temperature_c, payload_hash)
        VALUES (:reading_id, :device_id, :patient_id, :sequence, :observed_at, :heart_rate_bpm,
                :spo2_pct, :systolic_mmhg, :diastolic_mmhg, :temperature_c, :hash) RETURNING received_at
    """, values))
    asyncio.run(database_command("UPDATE patients SET latest_reading_id = :reading_id WHERE id = :patient_id", values))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    replay = client.post(f"{API}/readings", json=reading.model_dump(mode="json"))
    assert replay.status_code == 200
    assert replay.json()["assessment_id"] is None
    assert datetime.fromisoformat(replay.json()["received_at"]) == received
    snapshot = client.get(f"{API}/patients/{patient_id}").json()
    assert snapshot["latest_reading"]["reading_id"] == str(reading.reading_id)
    assert snapshot["current_assessment"] is None
    assert client.get(f"{API}/alerts").json()["items"] == []
