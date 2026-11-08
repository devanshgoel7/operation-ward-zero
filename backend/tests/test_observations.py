import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config

from app.core.database import create_engine
from app.models.observations import ObservationInput
from app.services.observations import expire_observations, record_observation
from conftest import database_command, frame

API = "/api/v1"
PATIENT = "20000000-0000-0000-0000-000000000001"
PATH = f"{API}/patients/{PATIENT}"
PRIMARY = "10000000-0000-0000-0000-000000000001"
BACKUP = "10000000-0000-0000-0000-000000000002"


def observation(**changes):
    return {"observation_id": str(uuid4()), "tag": "breathlessness", "present": True, "note": None} | changes


def post(client, body, actor=PRIMARY):
    return client.post(PATH+"/observations", json=body, headers={"X-Demo-Caregiver-Id": actor})


async def at_time(body, now):
    engine = create_engine()
    try:
        return await record_observation(engine, UUID(PATIENT), UUID(PRIMARY), ObservationInput.model_validate(body), now)
    finally:
        await engine.dispose()


async def expire(now):
    engine = create_engine()
    try:
        await expire_observations(engine, now)
    finally:
        await engine.dispose()


def test_current_trends_combination_clear_and_reading_replay(client):
    end = datetime.now(UTC)-timedelta(seconds=1)
    payloads = []
    for i in range(24):
        payload = frame(i+1) | {"observed_at": (end-timedelta(seconds=115-i*5)).isoformat(),
                                "spo2_pct": 99 if i<12 else 96, "heart_rate_bpm": 70 if i<12 else 90}
        payloads.append(payload)
        assert client.post(API+"/readings", json=payload).status_code == 201
    before = client.get(PATH).json()["current_assessment"]
    assert before["concern"] == "watch"
    assert {f["rule_id"] for f in before["findings"]} == {"spo2_pct.trend.watch", "heart_rate_bpm.trend.watch"}
    body = observation(note="Synthetic demo: caregiver reports difficulty breathing.")
    response = post(client, body, BACKUP)
    assert response.status_code == 201
    saved = response.json()
    assert saved["assessment"]["concern"] == "high"
    combo = next(f for f in saved["assessment"]["findings"] if f["rule_id"] == "breathlessness.spo2.high")
    assert {e["reading_id"] for e in combo["evidence"]} == {p["reading_id"] for p in payloads}
    assert combo["observations"] == [saved["observation"]]
    assert saved["observation"]["caregiver_id"] == BACKUP
    assert datetime.fromisoformat(saved["observation"]["expires_at"])-datetime.fromisoformat(saved["observation"]["created_at"]) == timedelta(minutes=10)
    receipt = client.post(API+"/readings", json=payloads[-1])
    assert receipt.status_code == 200 and receipt.json()["assessment_id"] == before["id"]
    assert post(client, body, BACKUP).json() == saved
    cleared = post(client, observation(present=False)).json()["assessment"]
    assert cleared["concern"] == "watch" and not any(f["observations"] for f in cleared["findings"])
    assert client.get(PATH).json()["active_observations"] == []
    assert client.get(PATH).json()["latest_reading"]["reading_id"] == payloads[-1]["reading_id"]
    [risk] = [a for a in client.get(API+"/alerts").json()["items"] if a["kind"] == "risk"]
    assert risk["peak_priority"] == "high" and risk["latest_assessment"]["id"] == cleared["id"]
    # Original evidence remains immutable after clearing.
    assert post(client, body, BACKUP).json() == saved


@pytest.mark.parametrize("tag", ["breathlessness", "dizziness", "reduced_intake"])
def test_each_tag_without_readings_and_false_clears(client, tag):
    response = post(client, observation(tag=tag))
    assert response.status_code == 201
    assessed = response.json()["assessment"]
    assert assessed["concern"] == "watch" and assessed["data_quality"] == "unavailable"
    assert assessed["reading_id"] is None
    snapshot = client.get(f"{API}/dashboard").json()["patients"][0]
    assert snapshot["latest_reading"] is None and snapshot["data_quality"] == "unavailable"
    assert snapshot["current_assessment"] == assessed
    [finding] = assessed["findings"]
    assert finding["rule_id"] == f"observation.{tag}.watch"
    assert finding["observations"] == [response.json()["observation"]]
    assert post(client, observation(tag=tag, present=False)).json()["assessment"]["concern"] is None
    assert client.get(PATH).json()["active_observations"] == []


def test_current_incomplete_threshold_combination_and_stale_exclusion(client):
    payload = frame() | {"spo2_pct": 93, "temperature_c": None}
    client.post(API+"/readings", json=payload).raise_for_status()
    assert post(client, observation()).json()["assessment"]["concern"] == "high"
    assert post(client, observation(present=False)).json()["assessment"]["concern"] == "watch"
    asyncio.run(database_command("UPDATE readings SET observed_at=observed_at-interval '1 minute'"))
    result = post(client, observation()).json()["assessment"]
    assert (result["concern"], result["data_quality"], result["reading_id"]) == ("watch", "stale", None)
    assert all(f["rule_id"] != "breathlessness.spo2.high" for f in result["findings"])


def test_clearing_one_tag_keeps_other_and_high_threshold(client):
    client.post(API+"/readings", json=frame() | {"heart_rate_bpm": 140}).raise_for_status()
    post(client, observation()).raise_for_status()
    post(client, observation(tag="dizziness")).raise_for_status()
    result = post(client, observation(present=False)).json()["assessment"]
    assert result["concern"] == "high"
    assert {f["rule_id"] for f in result["findings"]} == {"heart_rate_bpm.high.high", "observation.dizziness.watch"}


def test_expiry_boundary_once_and_no_resurrection(client):
    now = datetime.now(UTC)
    first, _ = asyncio.run(at_time(observation(), now))
    second, _ = asyncio.run(at_time(observation(), now+timedelta(seconds=1)))
    due = now+timedelta(minutes=10, seconds=1)
    asyncio.run(expire(due-timedelta(microseconds=1)))
    assert asyncio.run(database_command("SELECT count(*) FROM assessments WHERE trigger_kind='observation_expiry'")) == 0
    asyncio.run(expire(due))
    asyncio.run(expire(due+timedelta(seconds=5)))
    assert asyncio.run(database_command("SELECT count(*) FROM assessments WHERE trigger_kind='observation_expiry'")) == 1
    assert asyncio.run(database_command("SELECT context_expires_at FROM patients WHERE id=:id", {"id": PATIENT})) is None
    assert client.get(PATH).json()["current_assessment"]["concern"] is None
    # Latest false must not allow any older present to reappear, even with identical server times.
    asyncio.run(at_time(observation(tag="dizziness"), due))
    cleared, _ = asyncio.run(at_time(observation(tag="dizziness", present=False), due))
    assert not cleared.assessment.findings


def test_expiry_retains_a_current_threshold_and_startup_checks(client):
    client.post(API+"/readings", json=frame() | {"spo2_pct": 93}).raise_for_status()
    saved = post(client, observation()).json()
    asyncio.run(database_command("""UPDATE observations SET created_at=created_at-interval '11 minutes',
        expires_at=expires_at-interval '11 minutes'"""))
    asyncio.run(database_command("UPDATE patients SET context_expires_at=now()-interval '1 minute' WHERE id=:id", {"id": PATIENT}))
    from app.main import run_checks
    client.portal.call(run_checks, client.app)
    current = client.get(PATH).json()["current_assessment"]
    assert current["trigger_kind"] == "observation_expiry" and current["concern"] == "watch"
    assert [f["rule_id"] for f in current["findings"]] == ["spo2_pct.low.watch"]
    assert saved["assessment"]["concern"] == "high"
    client.portal.call(run_checks, client.app)
    assert client.get(PATH).json()["current_assessment"]["id"] == current["id"]


def test_replay_conflicts_concurrency_and_validation(client):
    body = observation(note="<script>uninterpreted text</script>")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: post(client, body), range(4)))
    assert sorted(r.status_code for r in results) == [200,200,200,201]
    assert all(r.json() == results[0].json() for r in results)
    for change in ({"note": "changed"}, {"present": False}, {"tag": "dizziness"}):
        assert post(client, body | change).status_code == 409
    assert post(client, body, BACKUP).status_code == 409
    other_path = PATH.replace(PATIENT, "20000000-0000-0000-0000-000000000002")
    assert client.post(other_path+"/observations", json=body, headers={"X-Demo-Caregiver-Id": PRIMARY}).status_code == 409
    assert post(client, observation(), str(uuid4())).status_code == 403
    for change in ({"present": "true"}, {"present": 1}, {"tag": "unknown"}, {"note": "x"*501}, {"created_at": "2026-01-01"}):
        assert post(client, observation(**change)).status_code == 422
    assert client.post(PATH+"/observations", json=observation()).status_code == 422
    assert client.post(f"{API}/patients/{uuid4()}/observations", json=observation(), headers={"X-Demo-Caregiver-Id": PRIMARY}).status_code == 404
    assert asyncio.run(database_command("SELECT count(*) FROM observations")) == 1
    assert asyncio.run(database_command("SELECT count(*) FROM assessments")) == 1
    assert asyncio.run(database_command("SELECT count(*) FROM alert_events")) == 1


def test_observation_failure_rolls_back_and_can_retry(client):
    before = client.get(PATH).json()
    body = observation()
    asyncio.run(database_command("ALTER TABLE alert_events ADD CONSTRAINT reject_context CHECK(false) NOT VALID"))
    try:
        assert post(client, body).status_code == 503
        assert client.get(PATH).json() == before
        assert asyncio.run(database_command("SELECT count(*) FROM observations")) == 0
        assert asyncio.run(database_command("SELECT count(*) FROM assessments")) == 0
    finally:
        asyncio.run(database_command("ALTER TABLE alert_events DROP CONSTRAINT reject_context"))
    assert post(client, body).status_code == 201


def test_reading_processes_due_expiry_without_leaving_stale_alert_evidence(client):
    client.post(API+"/readings", json=frame()).raise_for_status()
    post(client, observation()).raise_for_status()
    # Ingestion wins the patient lock before the periodic worker. Its assessment must
    # remove the expired contribution from both current state and latest alert evidence.
    asyncio.run(database_command("""UPDATE observations SET created_at=created_at-interval '11 minutes',
        expires_at=expires_at-interval '11 minutes'"""))
    payload = frame(2)
    result = client.post(API+"/readings", json=payload)
    assert result.status_code == 201
    [risk] = [a for a in client.get(API+"/alerts").json()["items"] if a["kind"] == "risk"]
    assert risk["latest_assessment"]["id"] == result.json()["assessment_id"]
    assert risk["latest_assessment"]["concern"] == "none"
    assert risk["original_assessment"]["findings"][0]["observations"]
    asyncio.run(expire(datetime.now(UTC)+timedelta(minutes=1)))
    assert asyncio.run(database_command("SELECT count(*) FROM assessments WHERE trigger_kind='observation_expiry'")) == 0


def test_concurrent_reading_observation_and_historical_scope(client):
    payload = frame() | {"spo2_pct": 93}
    with ThreadPoolExecutor(max_workers=2) as pool:
        reading = pool.submit(client.post, API+"/readings", json=payload)
        observed = pool.submit(post, client, observation())
        assert reading.result().status_code == observed.result().status_code == 201
    assert client.get(PATH).json()["current_assessment"]["concern"] == "high"
    before = client.get(PATH).json()["current_assessment"]
    historical = frame(2) | {"spo2_pct": 93, "observed_at": (datetime.now(UTC)-timedelta(minutes=5)).isoformat()}
    assert client.post(API+"/readings", json=historical).status_code == 201
    assert client.get(PATH).json()["current_assessment"] == before
    alerts = client.get(API+"/alerts").json()["items"]
    assert sum(a["kind"] == "risk" for a in alerts) == 1
    review = next(a for a in alerts if a["kind"] == "delayed_review")
    assert review["latest_assessment"]["concern"] == "watch"
    assert not review["latest_assessment"]["trend_summary"]
    assert not any(f["observations"] for f in review["latest_assessment"]["findings"])


def test_upgrade_preserves_m3_reading_assessment(client):
    config = Config("alembic.ini")
    command.downgrade(config, "0006_data_quality")
    payload = frame()
    values = {"id": payload["reading_id"], "patient": PATIENT, "device": payload["device_id"]}
    asyncio.run(database_command("""INSERT INTO readings (id,patient_id,device_id,sequence,observed_at,payload_hash)
        VALUES (:id,:patient,:device,1,now(),'legacy')""", values))
    legacy = asyncio.run(database_command("""INSERT INTO assessments (patient_id,reading_id,scope,concern,data_quality,findings,rule_version)
        VALUES (:patient,:id,'current','watch','incomplete','[]','demo-thresholds-v1') RETURNING id""", values))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert asyncio.run(database_command("SELECT id FROM assessments WHERE reading_id=:id AND trigger_kind='reading'", values)) == legacy
    assert asyncio.run(database_command("SELECT trend_summary FROM assessments WHERE id=:id", {"id": legacy})) == []
