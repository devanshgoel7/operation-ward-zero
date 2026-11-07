import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import create_engine
from app.services.alerts import escalate_due
from app.services.quality import check_freshness
from conftest import database_command, frame

API = "/api/v1"
PATIENT = "20000000-0000-0000-0000-000000000001"
PATH = f"{API}/patients/{PATIENT}"


async def tick(now: datetime) -> None:
    engine = create_engine()
    try:
        await check_freshness(engine, now)
    finally:
        await engine.dispose()


def test_gap_and_three_consecutive_current_complete_readings(client: TestClient) -> None:
    assert client.get(PATH).json()["data_quality"] == "unavailable"
    asyncio.run(database_command("UPDATE patients SET monitoring_started_at=now()-interval '40 seconds'"))
    started = asyncio.run(database_command("SELECT monitoring_started_at FROM patients WHERE id=:id", {"id": PATIENT}))
    asyncio.run(tick(started + timedelta(seconds=30)))
    assert not client.get(f"{API}/alerts").json()["items"]
    for _ in range(2):
        asyncio.run(tick(started + timedelta(seconds=31)))
    [gap] = client.get(f"{API}/alerts", params={"patient_id": PATIENT}).json()["items"]
    assert gap["kind"] == "monitoring_gap" and gap["latest_assessment"] is None
    gap_path = f"{API}/alerts/{gap['id']}"
    assert client.post(gap_path + "/acknowledge", json={"command_id": str(uuid4())},
                       headers={"X-Demo-Caregiver-Id": gap["assignee_id"]}).is_success
    for n in range(1, 7):
        payload = frame(n)
        if n == 2:
            payload["temperature_c"] = None
        if n == 5:
            payload["observed_at"] = (started - timedelta(minutes=2)).isoformat()
        assert client.post(f"{API}/readings", json=payload).status_code == 201
        assert client.post(f"{API}/readings", json=payload).status_code == 200
        expected = "resolved" if n >= 6 else "acknowledged"
        # Samples 3 and 4 count; historical sample 5 and all replays do not.
        assert client.get(gap_path).json()["status"] == expected
    detail = client.get(gap_path).json()
    assert detail["resolved_at"] and [e["event_type"] for e in detail["events"]] == ["opened","acknowledged","resolved"]
    assert gap["id"] not in [a["id"] for a in client.get(f"{API}/dashboard").json()["active_alerts"]]


def test_stale_display_last_concern_and_delayed_evidence(client: TestClient) -> None:
    now = datetime.now(UTC)
    def send(n: int, age: int, **values):
        payload = frame(n) | {"observed_at": (now - timedelta(seconds=age)).isoformat()} | values
        assert client.post(f"{API}/readings", json=payload).status_code == 201
        return payload
    original = send(1, 15, spo2_pct=93)
    snapshot = client.get(PATH).json()
    assert snapshot["delivery_delayed"] and snapshot["last_known_concern"] == "watch"
    send(2, 5, temperature_c=None)
    incomplete = client.get(PATH).json()
    assert incomplete["data_quality"] == "incomplete" and incomplete["current_assessment"]["concern"] is None
    assert incomplete["last_known_observed_at"] == snapshot["last_known_observed_at"]
    historical = [send(3, 60, spo2_pct=93), send(4, 12, spo2_pct=88)]
    assert client.get(PATH).json() == incomplete
    [review] = [a for a in client.get(f"{API}/dashboard").json()["active_alerts"] if a["kind"] == "delayed_review"]
    assert review["revision"] == 2 and review["peak_priority"] == "high"
    assert [review[k]["reading_id"] for k in ("original_assessment","latest_assessment")] == [p["reading_id"] for p in historical]
    assert review["latest_assessment"]["scope"] == "historical"
    history_ids = {r["reading_id"] for r in client.get(PATH + "/readings").json()["items"]}
    assert all(p["reading_id"] in history_ids for p in [original, *historical])
    # Move this fixture's observation clock back, leaving receipt timestamps untouched.
    asyncio.run(database_command("UPDATE readings SET observed_at=observed_at-interval '1 minute'"))
    asyncio.run(database_command("""UPDATE patients SET last_complete_at=last_complete_at-interval '1 minute',
        monitoring_started_at=monitoring_started_at-interval '1 minute'"""))
    stale = client.get(PATH).json()
    assert stale["data_quality"] == "stale" and stale["current_assessment"] is None and stale["last_known_concern"] == "watch"
    send(5, 0, spo2_pct=88, temperature_c=None)
    latest = client.get(PATH).json()
    assert latest["data_quality"] == "stale" and latest["current_assessment"]["concern"] == "high"


def test_worker_overdue(client: TestClient) -> None:
    client.app.state.worker_last_success_at = datetime.now(UTC) - timedelta(seconds=16)
    response = client.get("/health/ready")
    assert response.status_code == 503 and response.json()["error"]["code"] == "worker_overdue"


def test_acknowledgement_competes_with_existing_escalation(client: TestClient) -> None:
    assert client.post(f"{API}/readings", json=frame() | {"spo2_pct": 88}).status_code == 201
    [alert] = client.get(f"{API}/alerts").json()["items"]
    path = f"{API}/alerts/{alert['id']}"
    asyncio.run(database_command("UPDATE alerts SET escalation_due_at=now()"))
    async def escalate():
        engine = create_engine()
        try:
            await escalate_due(engine)
        finally:
            await engine.dispose()
    with ThreadPoolExecutor() as pool:
        moved = pool.submit(asyncio.run, escalate())
        ack = client.post(path + "/acknowledge", headers={"X-Demo-Caregiver-Id": alert["assignee_id"]},
                          json={"command_id": str(uuid4())})
        moved.result()
    detail = client.get(path).json()
    if ack.status_code == 200:
        assert detail["status"] == "acknowledged" and detail["assignee_id"] == alert["assignee_id"]
        expected = "acknowledged"
    else:
        assert ack.status_code == 403 and detail["status"] == "open" and detail["assignee_id"] != alert["assignee_id"]
        expected = "escalated"
    assert [e["event_type"] for e in detail["events"]] == ["opened", expected]

def test_m2_upgrade_surfaces_saved_historical_findings(client: TestClient) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    command.downgrade(config, "0005_escalation")
    for n, level in enumerate(["watch", "high"], start=1):
        reading = frame(n)
        values = {"id": reading["reading_id"], "device": reading["device_id"], "patient": PATIENT, "n": n,
                  "level": level}
        asyncio.run(database_command("""INSERT INTO readings (id,patient_id,device_id,sequence,observed_at,payload_hash)
            VALUES (:id,:patient,:device,:n,now()-interval '5 minutes','fixture')""", values))
        asyncio.run(database_command("""INSERT INTO assessments (patient_id,reading_id,scope,concern,data_quality,
            rule_version,findings) VALUES (:patient,:id,'historical',:level,'incomplete','demo-thresholds-v1','[]')""", values))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    [review] = client.get(f"{API}/dashboard").json()["active_alerts"]
    assert review["kind"] == "delayed_review" and review["peak_priority"] == "high" and review["revision"] == 2
    assert review["original_assessment"]["concern"] == "watch" and review["latest_assessment"]["concern"] == "high"
    assert client.get(PATH).json()["current_assessment"] is None
    assert [e["event_type"] for e in client.get(f"{API}/alerts/{review['id']}").json()["events"]] == ["opened", "updated"]
