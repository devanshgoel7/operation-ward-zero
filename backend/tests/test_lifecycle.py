"""M5 state transitions use real PostgreSQL and explicit evaluation times."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.core.database import create_engine
from app.models.alerts import Resolve
from app.services.alerts import acknowledge, escalate_due, resolve
from app.services.errors import MonitoringError
from conftest import database_command, frame

API = "/api/v1"
PRIMARY = "10000000-0000-0000-0000-000000000001"
BACKUP = "10000000-0000-0000-0000-000000000002"
PATIENT = "20000000-0000-0000-0000-000000000001"


def send(client, n=1, **values):
    payload = frame(n) | values
    response = client.post(API+"/readings", json=payload)
    assert response.status_code == 201, response.text
    return payload


def episode(client, kind="risk"):
    return next(a for a in client.get(API+"/alerts").json()["items"] if a["kind"] == kind)


def action(client, alert, kind="acknowledge", actor=PRIMARY, body=None):
    return client.post(f"{API}/alerts/{alert['id']}/{kind}",
                       headers={"X-Demo-Caregiver-Id": actor}, json=body or {"command_id": str(uuid4())})


async def call(service, *args):
    engine = create_engine()
    try:
        return await service(engine, *args)
    finally:
        await engine.dispose()


def detail(client, alert):
    return client.get(f"{API}/alerts/{alert['id']}").json()


@pytest.mark.parametrize("oxygen,seconds", [(93, 60), (88, 30)])
def test_exact_deadline_one_handoff_and_response_timing(client, oxygen, seconds):
    send(client, spo2_pct=oxygen)
    alert = episode(client)
    due = datetime.fromisoformat(alert["escalation_due_at"])
    assert due-datetime.fromisoformat(alert["response_started_at"]) == timedelta(seconds=seconds)
    asyncio.run(call(escalate_due, due-timedelta(microseconds=1)))
    assert detail(client, alert)["assignee_id"] == PRIMARY
    for _ in range(3):
        asyncio.run(call(escalate_due, due))
    saved = detail(client, alert)
    assert saved["assignee_id"] == BACKUP and saved["escalation_due_at"] is None
    assert saved["escalated_at"] == due.isoformat().replace("+00:00", "Z")
    assert [e["event_type"] for e in saved["events"]] == ["opened", "escalated"]
    ack = asyncio.run(call(acknowledge, UUID(alert["id"]), UUID(BACKUP), uuid4(), due+timedelta(seconds=7)))
    assert ack.status == "acknowledged"
    assert detail(client, alert)["events"][-1]["details"] == {
        "response_seconds": seconds+7, "assignment_response_seconds": 7}


def test_ack_cancels_deadline_and_higher_priority_reopens_after_incomplete(client):
    send(client, spo2_pct=93)
    alert = episode(client)
    old_command = {"command_id": str(uuid4())}
    assert action(client, alert, body=old_command).status_code == 200
    due = datetime.fromisoformat(alert["escalation_due_at"])
    asyncio.run(call(escalate_due, due))
    assert detail(client, alert)["escalation_due_at"] is None
    send(client, 2, temperature_c=None)
    send(client, 3, spo2_pct=88)
    reopened = detail(client, alert)
    assert reopened["status"] == "open" and reopened["acknowledged_at"] is None
    assert reopened["peak_priority"] == "high"
    new_due = datetime.fromisoformat(reopened["escalation_due_at"])
    assert new_due-datetime.fromisoformat(reopened["response_started_at"]) == timedelta(seconds=30)
    asyncio.run(call(escalate_due, new_due))
    # A lost old acknowledgement response must not acknowledge the new cycle,
    # even after the episode has moved to a different caregiver.
    replay = action(client, alert, body=old_command)
    assert replay.status_code == 200 and replay.json()["status"] == "open"
    assert action(client, alert).status_code == 403
    assert action(client, alert, actor=BACKUP).status_code == 200
    assert sum(e["event_type"] == "acknowledged" for e in detail(client, alert)["events"]) == 2


def test_risk_resolution_conditions_replay_history_and_new_episode(client):
    send(client, spo2_pct=88)
    alert = episode(client)
    body = {"command_id": str(uuid4()), "note": "<b>Recovered synthetic readings reviewed</b>"}
    assert action(client, alert, "resolve", body=body).status_code == 409
    assert action(client, alert).status_code == 200
    assert action(client, alert, "resolve", actor=BACKUP, body=body).status_code == 403
    for n in (2, 3):
        payload = send(client, n)
        assert client.post(API+"/readings", json=payload).status_code == 200
        assert action(client, alert, "resolve", body=body).status_code == 409
    send(client, 4, temperature_c=None)
    assert detail(client, alert)["recovery_count"] == 0
    send(client, 5)
    # Historical input never advances or resets current recovery.
    old = datetime.fromisoformat(frame()["observed_at"])-timedelta(minutes=5)
    send(client, 6, observed_at=old.isoformat(), spo2_pct=88)
    assert detail(client, alert)["recovery_count"] == 1
    send(client, 7)
    send(client, 8)
    assert detail(client, alert)["recovery_count"] == 3
    for note in ("", "  ", "x"*501):
        assert action(client, alert, "resolve", body=body | {"note": note}).status_code == 422
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: action(client, alert, "resolve", body=body), range(3)))
    assert all(r.status_code == 200 for r in results)
    saved = detail(client, alert)
    assert saved["status"] == "resolved" and saved["resolved_by"] == PRIMARY
    assert saved["acknowledged_at"] and saved["resolved_at"]
    assert saved["original_assessment"] == alert["original_assessment"]
    assert saved["peak_priority"] == "high"
    events = [e for e in saved["events"] if e["event_type"] == "resolved"]
    assert len(events) == 1 and events[0]["details"]["note"] == body["note"]
    assert action(client, alert, "resolve", body=body | {"note": "changed"}).status_code == 409
    assert action(client, alert, body={"command_id": body["command_id"]}).status_code == 409
    assert action(client, alert, "resolve", body=body | {"command_id": str(uuid4())}).status_code == 409
    assert all(a["id"] != alert["id"] for a in client.get(API+"/dashboard").json()["active_alerts"])
    send(client, 9, spo2_pct=88)
    assert episode(client)["id"] != alert["id"]


def test_context_blocks_recovery_and_clear_does_not_count(client):
    send(client, spo2_pct=88)
    alert = episode(client)
    assert action(client, alert).status_code == 200
    observation = {"observation_id": str(uuid4()), "tag": "dizziness", "present": True}
    path = f"{API}/patients/{PATIENT}/observations"
    assert client.post(path, json=observation, headers={"X-Demo-Caregiver-Id": PRIMARY}).status_code == 201
    for n in (2, 3, 4):
        send(client, n)
    assert detail(client, alert)["recovery_count"] == 0
    assert client.post(path, json=observation | {"observation_id": str(uuid4()), "present": False},
                       headers={"X-Demo-Caregiver-Id": PRIMARY}).status_code == 201
    assert detail(client, alert)["recovery_count"] == 0
    for n in (5, 6, 7):
        send(client, n)
    assert detail(client, alert)["recovery_count"] == 3


def test_freshness_boundary_and_restart_of_recovery(client):
    send(client, spo2_pct=88)
    alert = episode(client)
    action(client, alert).raise_for_status()
    for n in (2, 3, 4):
        send(client, n)
    saved = detail(client, alert)
    observed = datetime.fromisoformat(saved["recovery_observed_at"])
    body = Resolve(command_id=uuid4(), note="Freshness boundary")
    with pytest.raises(MonitoringError, match="three consecutive"):
        asyncio.run(call(resolve, UUID(alert["id"]), UUID(PRIMARY), body,
                         observed+timedelta(seconds=30, microseconds=1)))
    # Rejected command leaves no event and can safely retry.
    result = asyncio.run(call(resolve, UUID(alert["id"]), UUID(PRIMARY), body, observed+timedelta(seconds=30)))
    assert result.status == "resolved"


def test_staleness_breaks_recovery_without_worker(client):
    send(client, spo2_pct=88)
    alert = episode(client)
    for n in (2, 3):
        send(client, n)
    asyncio.run(database_command("UPDATE alerts SET recovery_observed_at=now()-interval '31 seconds'"))
    send(client, 4)
    assert detail(client, alert)["recovery_count"] == 1


def test_delayed_review_note_only_and_monitoring_gap_automatic(client):
    old = datetime.fromisoformat(frame()["observed_at"])-timedelta(minutes=5)
    send(client, observed_at=old.isoformat(), spo2_pct=88)
    alert = episode(client, "delayed_review")
    body = {"command_id": str(uuid4()), "note": "Reviewed original observation time"}
    assert action(client, alert, "resolve", body=body).status_code == 409
    action(client, alert).raise_for_status()
    assert action(client, alert, "resolve", body=body).status_code == 200
    from app.services.quality import check_freshness
    asyncio.run(call(check_freshness, old+timedelta(minutes=6)))
    gap = episode(client, "monitoring_gap")
    action(client, gap).raise_for_status()
    response = action(client, gap, "resolve", body=body | {"command_id": str(uuid4())})
    assert response.status_code == 409 and response.json()["error"]["code"] == "automatic_resolution"


def test_resolution_audit_failure_rolls_back(client):
    send(client, spo2_pct=88)
    alert = episode(client)
    action(client, alert).raise_for_status()
    for n in (2, 3, 4):
        send(client, n)
    body = {"command_id": str(uuid4()), "note": "Recovery checked"}
    asyncio.run(database_command("ALTER TABLE alerts ADD CONSTRAINT reject_resolution CHECK(status<>'resolved') NOT VALID"))
    try:
        assert action(client, alert, "resolve", body=body).status_code == 503
        assert detail(client, alert)["status"] == "acknowledged"
        assert not any(e["event_type"] == "resolved" for e in detail(client, alert)["events"])
    finally:
        asyncio.run(database_command("ALTER TABLE alerts DROP CONSTRAINT reject_resolution"))
    assert action(client, alert, "resolve", body=body).status_code == 200


def test_resolution_competes_with_new_high(client):
    send(client, spo2_pct=93)
    alert = episode(client)
    action(client, alert).raise_for_status()
    for n in (2, 3, 4):
        send(client, n)
    with ThreadPoolExecutor(max_workers=2) as pool:
        resolving = pool.submit(action, client, alert, "resolve", PRIMARY,
                                {"command_id": str(uuid4()), "note": "Concurrent recovery"})
        send(client, 5, spo2_pct=88)
        result = resolving.result()
    active = [a for a in client.get(API+"/dashboard").json()["active_alerts"] if a["kind"] == "risk"]
    assert len(active) == 1 and active[0]["status"] == "open" and active[0]["peak_priority"] == "high"
    if result.status_code == 200:
        assert active[0]["id"] != alert["id"] and detail(client, alert)["status"] == "resolved"
    else:
        assert result.status_code == 409 and active[0]["id"] == alert["id"]


def test_watch_deadline_shortens_without_extending(client):
    send(client, spo2_pct=93)
    alert = episode(client)
    send(client, 2, spo2_pct=88)
    due = detail(client, alert)["escalation_due_at"]
    assert due < alert["escalation_due_at"]
    send(client, 3, spo2_pct=93)
    assert detail(client, alert)["escalation_due_at"] == due


def test_lowered_concern_and_incomplete_frame_cannot_hide_priority_rise(client):
    send(client, spo2_pct=88)
    alert = episode(client)
    action(client, alert).raise_for_status()
    send(client, 2, spo2_pct=93)
    send(client, 3, temperature_c=None)
    send(client, 4, spo2_pct=88)
    saved = detail(client, alert)
    assert saved["status"] == "open" and saved["acknowledged_at"] is None
    assert saved["events"][-1]["event_type"] == "reopened"


def test_supported_trend_prevents_risk_recovery(client):
    end = datetime.fromisoformat(frame()["observed_at"])-timedelta(seconds=1)
    for n in range(24):
        send(client, n+1, observed_at=(end-timedelta(seconds=115-5*n)).isoformat(),
             spo2_pct=99 if n<12 else 96)
    alert = episode(client)
    action(client, alert).raise_for_status()
    for n in (25, 26, 27):
        send(client, n, spo2_pct=96)
    saved = detail(client, alert)
    assert saved["recovery_count"] == 0
    assert any(f["rule_id"] == "spo2_pct.trend.watch" for f in saved["latest_assessment"]["findings"])
    assert action(client, alert, "resolve", body={"command_id": str(uuid4()), "note": "Trend still firing"}).status_code == 409


def test_m4_upgrade_preserves_pending_deadline_and_command_replay(client):
    from alembic import command
    from alembic.config import Config

    # Create an actual M4 schema fixture, including the old command representation.
    config = Config("alembic.ini")
    command.downgrade(config, "0007_context")
    reading = frame()
    values = {"reading": reading["reading_id"], "patient": PATIENT,
              "actor": PRIMARY, "command": str(uuid4())}
    asyncio.run(database_command("""INSERT INTO readings (id,patient_id,device_id,sequence,observed_at,payload_hash)
        VALUES (:reading,:patient,'30000000-0000-0000-0000-000000000001',1,now(),'fixture')""", values))
    assessment = asyncio.run(database_command("""INSERT INTO assessments
        (patient_id,reading_id,scope,concern,data_quality,findings,rule_version)
        VALUES (:patient,:reading,'current','watch','fresh','[]','demo-context-v1') RETURNING id""", values))
    values["assessment"] = assessment
    alert_id = asyncio.run(database_command("""INSERT INTO alerts
        (patient_id,kind,status,peak_priority,assignee_id,original_assessment_id,latest_assessment_id,
         acknowledged_at,acknowledged_by) VALUES (:patient,'risk','acknowledged','watch',:actor,
         :assessment,:assessment,now(),:actor) RETURNING id""", values))
    values["alert"] = alert_id
    asyncio.run(database_command("""INSERT INTO alert_events (alert_id,event_type,caregiver_id,command_id)
        VALUES (:alert,'acknowledged',:actor,:command)""", values))
    asyncio.run(database_command("UPDATE alerts SET opened_at=now()-interval '2 minutes' WHERE id=:alert", values))
    asyncio.run(database_command("""INSERT INTO alert_events (alert_id,event_type,occurred_at)
        VALUES (:alert,'opened',now()-interval '2 minutes'),
               (:alert,'escalated',now()-interval '90 seconds'),
               (:alert,'reopened',now()-interval '1 minute')""", values))
    pending_id = asyncio.run(database_command("""INSERT INTO alerts
        (patient_id,kind,status,peak_priority,assignee_id,original_assessment_id,latest_assessment_id,escalation_due_at)
        VALUES (:patient,'delayed_review','open','watch',:actor,:assessment,:assessment,now()+interval '1 minute')
        RETURNING id""", values))
    deadline = asyncio.run(database_command("SELECT escalation_due_at FROM alerts WHERE id=:id", {"id": pending_id}))
    asyncio.run(database_command("""INSERT INTO alert_events (alert_id,event_type,assessment_id)
        VALUES (:id,'opened',:assessment)""", {"id": pending_id, "assessment": assessment}))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    saved = client.get(f"{API}/alerts/{alert_id}").json()
    assert saved["recovery_count"] == 0 and saved["response_started_at"] > saved["opened_at"]
    assert saved["response_started_at"] == next(e["occurred_at"] for e in saved["events"] if e["event_type"] == "reopened")
    assert saved["escalated_at"] is None  # An earlier cycle's backup handoff must not leak into this one.
    assert saved["original_assessment"]["id"] == str(assessment)
    assert action(client, saved, body={"command_id": values["command"]}).status_code == 200
    assert len(detail(client, saved)["events"]) == 4
    pending = client.get(f"{API}/alerts/{pending_id}").json()
    assert pending["status"] == "open" and pending["assignee_id"] == PRIMARY
    assert datetime.fromisoformat(pending["escalation_due_at"]) == deadline
