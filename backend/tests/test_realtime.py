"""M6: notifications never replace committed state or delay ingestion."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.database import create_engine
from app.main import app
from app.services.alerts import escalate_due
from app.services.observations import expire_observations
from app.services.quality import check_freshness
from app.services.realtime import RealtimeHub, message
from conftest import database_command, frame

PATIENT = "20000000-0000-0000-0000-000000000001"
PRIMARY = "10000000-0000-0000-0000-000000000001"
API = "/api/v1"


def test_reading_hints_follow_commit_and_replay_is_silent(client, monkeypatch):
    events = []
    payload = frame() | {"spo2_pct": 88}

    def capture(kind, **fields):
        # Inspect from a separate PostgreSQL connection at publication time.
        with ThreadPoolExecutor(1) as pool:
            count = pool.submit(lambda: asyncio.run(database_command(
                "SELECT count(*) FROM readings WHERE id=:id", {"id": payload["reading_id"]}))).result()
        assert count == 1
        events.append(message(kind, **fields))

    monkeypatch.setattr(app.state.realtime, "publish", capture)
    assert client.post(API+"/readings", json=payload).status_code == 201
    assert [e["type"] for e in events] == ["patient.updated", "alert.updated"]
    assert all(e["patient_id"] == PATIENT for e in events)
    assert client.post(API+"/readings", json=payload).status_code == 200
    assert len(events) == 2


def test_rolled_back_ingestion_does_not_publish(client, monkeypatch):
    events = []
    monkeypatch.setattr(app.state.realtime, "publish", lambda *args, **kw: events.append(args))
    asyncio.run(database_command("ALTER TABLE alert_events ADD CONSTRAINT reject_hint CHECK (false) NOT VALID"))
    assert client.post(API+"/readings", json=frame() | {"spo2_pct": 88}).status_code == 503
    assert events == []
    assert asyncio.run(database_command("SELECT count(*) FROM readings")) == 0


def test_notification_failure_cannot_change_successful_receipt(client, monkeypatch):
    def fail(*args, **kw):
        raise RuntimeError("notification fault")
    monkeypatch.setattr(app.state.realtime, "publish", fail)
    payload = frame()
    assert client.post(API+"/readings", json=payload).status_code == 201
    assert client.get(f"{API}/patients/{PATIENT}").json()["latest_reading"]["reading_id"] == payload["reading_id"]


def test_observation_and_caregiver_hints_replay_and_rejection(client, monkeypatch):
    events = []
    monkeypatch.setattr(app.state.realtime, "publish", lambda kind, **kw: events.append(message(kind, **kw)))
    body = {"observation_id": str(uuid4()), "tag": "dizziness", "present": True, "note": "M6"}
    headers = {"X-Demo-Caregiver-Id": PRIMARY}
    assert client.post(f"{API}/patients/{PATIENT}/observations", json=body, headers=headers).status_code == 201
    assert [e["type"] for e in events] == ["patient.updated", "alert.updated"]
    events.clear()
    assert client.post(f"{API}/patients/{PATIENT}/observations", json=body, headers=headers).status_code == 200
    assert events == []
    alert = client.get(API+"/alerts").json()["items"][0]
    path = f"{API}/alerts/{alert['id']}"
    command = {"command_id": str(uuid4())}
    assert client.post(path+"/acknowledge", json=command, headers=headers).status_code == 200
    assert events[-1]["alert_id"] == alert["id"] and events[-1]["revision"] > alert["revision"]
    events.clear()
    assert client.post(path+"/acknowledge", json=command, headers=headers).status_code == 200
    assert client.post(path+"/resolve", json={"command_id": str(uuid4()), "note": "premature"}, headers=headers).status_code == 409
    assert events == []
    body.update(observation_id=str(uuid4()), present=False)
    assert client.post(f"{API}/patients/{PATIENT}/observations", json=body, headers=headers).status_code == 201
    for n in range(1, 4):
        assert client.post(API+"/readings", json=frame(n)).status_code == 201
    events.clear()
    resolve = {"command_id": str(uuid4()), "note": "Recovered"}
    assert client.post(path+"/resolve", json=resolve, headers=headers).status_code == 200
    assert [e["type"] for e in events] == ["alert.updated"]
    assert client.get(path).json()["status"] == "resolved"
    events.clear()
    assert client.post(path+"/resolve", json=resolve, headers=headers).status_code == 200
    assert events == []


def test_periodic_commits_publish_gap_expiry_and_escalation(client):
    body = {"observation_id": str(uuid4()), "tag": "dizziness", "present": True}
    assert client.post(f"{API}/patients/{PATIENT}/observations", json=body,
                       headers={"X-Demo-Caregiver-Id": PRIMARY}).status_code == 201

    async def check():
        hub = RealtimeHub()
        subscriber = hub.subscribe()
        engine = create_engine()
        try:
            now = datetime.now(UTC) + timedelta(minutes=11)
            for service in (check_freshness, expire_observations, escalate_due):
                await service(engine, now, hub=hub)
                assert not subscriber.queue.empty(), service.__name__
                while not subscriber.queue.empty():
                    event = subscriber.queue.get_nowait()
                    assert event["type"] in ("patient.updated", "alert.updated")
                await service(engine, now, hub=hub)
                assert subscriber.queue.empty(), "A repeated pass must not repeat transition hints"
        finally:
            await engine.dispose()
    asyncio.run(check())


def test_bounded_queue_evicts_only_slow_subscriber():
    async def check():
        hub = RealtimeHub()
        slow, fast = hub.subscribe(), hub.subscribe()
        for _ in range(33):
            hub.publish("patient.updated")
            assert fast.queue.get_nowait()["type"] == "patient.updated"
        assert slow.queue.qsize() == 32 and slow.overflow.is_set()
        assert slow not in hub.clients and fast in hub.clients
        hub.unsubscribe(fast)
        assert not hub.clients
    asyncio.run(check())


def test_socket_heartbeat_multiple_clients_and_cleanup(client, monkeypatch):
    monkeypatch.setattr("app.api.realtime.HEARTBEAT_SECONDS", .05)
    with client.websocket_connect(API+"/ws") as first, client.websocket_connect(API+"/ws") as second:
        assert first.receive_json()["type"] == "heartbeat"
        payload = frame()
        assert client.post(API+"/readings", json=payload).status_code == 201
        for socket in (first, second):
            event = socket.receive_json()
            while event["type"] == "heartbeat":
                event = socket.receive_json()
            assert event["type"] == "patient.updated" and event["patient_id"] == PATIENT
            assert client.get(f"{API}/patients/{PATIENT}").json()["latest_reading"]["reading_id"] == payload["reading_id"]
    assert not app.state.realtime.clients


@pytest.mark.parametrize("overflow", [False, True])
def test_blocked_socket_is_closed_and_cleaned_up(overflow, monkeypatch):
    from app.api.realtime import updates
    from types import SimpleNamespace
    monkeypatch.setattr("app.api.realtime.SEND_TIMEOUT_SECONDS", .02)
    monkeypatch.setattr("app.api.realtime.HEARTBEAT_SECONDS", .01)

    async def check():
        hub = RealtimeHub()
        class Socket:
            app = SimpleNamespace(state=SimpleNamespace(realtime=hub))
            code = None
            async def accept(self): pass
            async def send_json(self, event): await asyncio.Event().wait()
            async def receive(self): await asyncio.Event().wait()
            async def close(self, code): self.code = code
        socket = Socket()
        task = asyncio.create_task(updates(socket))
        await asyncio.sleep(0)
        if overflow:
            for _ in range(33): hub.publish("patient.updated")
        await asyncio.wait_for(task, timeout=1)
        assert not hub.clients
        assert socket.code == (1013 if overflow else 1000)
    asyncio.run(check())
