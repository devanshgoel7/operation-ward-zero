"""Exercise the HTTP contract against a disposable database on the real Compose PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import frame


def test_repeatable_seeds_and_three_patient_path(client: TestClient) -> None:
    dashboard = client.get("/api/v1/dashboard").json()
    patients = dashboard["patients"]
    assert len(patients) == 3
    assert len(dashboard["caregivers"]) == 2
    assert len({p["patient"]["device_id"] for p in patients}) == 3
    for snapshot in patients:
        patient = snapshot["patient"]
        payload = dict(frame(10), device_id=patient["device_id"])
        response = client.post("/api/v1/readings", json=payload)
        assert response.status_code == 201, response.text
        stored = client.get(f"/api/v1/patients/{patient['id']}").json()["latest_reading"]
        assert stored["patient_id"] == patient["id"]
        assert stored["reading_id"] == payload["reading_id"]
        assert stored["received_at"] == response.json()["received_at"]
        assert stored["heart_rate_bpm"] == payload["heart_rate_bpm"]


def test_concurrent_replays_and_conflicting_identities(client: TestClient) -> None:
    payload = frame(11)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post("/api/v1/readings", json=payload), range(4)))
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 201]
    assert len({r.json()["received_at"] for r in responses}) == 1
    assert {r.json()["disposition"] for r in responses} == {"accepted", "duplicate"}
    for change in ({"heart_rate_bpm": 88}, {"reading_id": str(uuid4())},
                   {"sequence": 12}, {"device_id": "30000000-0000-0000-0000-000000000002"}):
        response = client.post("/api/v1/readings", json=payload | change)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "identity_conflict"
    patient_id = "20000000-0000-0000-0000-000000000001"
    history = client.get(f"/api/v1/patients/{patient_id}/readings").json()["items"]
    assert [r["reading_id"] for r in history].count(payload["reading_id"]) == 1


@pytest.mark.parametrize("change", [
    {"reading_id": "bad"}, {"sequence": 0}, {"sequence": True}, {"device_id": str(uuid4())},
    {"observed_at": "2026-01-01T00:00:00"}, {"observed_at": "2100-01-01T00:00:00Z"},
    {"heart_rate_bpm": -1}, {"spo2_pct": 101}, {"systolic_mmhg": 70},
    {"temperature_c": "NaN"}, {"diastolic_mmhg": 0}, {"patient_id": str(uuid4())},
])
def test_validation(client: TestClient, change: dict) -> None:
    response = client.post("/api/v1/readings", json=frame() | change)
    assert response.status_code == 422
    assert response.json()["request_id"]


def test_sensor_key_and_required_nullable_fields(client: TestClient) -> None:
    payload = frame(21)
    response = client.post("/api/v1/readings", json=payload, headers={"X-Simulator-Key": "wrong"})
    assert response.status_code == 403
    del payload["temperature_c"]
    assert client.post("/api/v1/readings", json=payload).status_code == 422
    assert client.post("/api/v1/readings", json=payload | {"temperature_c": None}).status_code == 201


def test_history_window_and_order(client: TestClient) -> None:
    patient = client.get("/api/v1/dashboard").json()["patients"][2]["patient"]
    path = f"/api/v1/patients/{patient['id']}"
    end = datetime.now(UTC) - timedelta(days=1)
    ids = []
    for n in range(3):
        payload = frame(30 + n) | {"observed_at": (end - timedelta(seconds=n)).isoformat(),
                                  "device_id": patient["device_id"]}
        assert client.post("/api/v1/readings", json=payload).status_code == 201
        ids.append(payload["reading_id"])
    params = {"from": (end - timedelta(seconds=2)).isoformat(), "to": end.isoformat(), "limit": 2}
    page = client.get(path + "/readings", params=params).json()
    assert [item["reading_id"] for item in page["items"]] == ids[:2]
    last = client.get(path + "/readings", params=params | {"cursor": page["next_cursor"]}).json()
    assert [item["reading_id"] for item in last["items"]] == ids[2:]
    assert last["next_cursor"] is None
    assert not set(ids).intersection(r["reading_id"] for r in client.get(path + "/readings").json()["items"])
    for invalid in ({"cursor": "invalid"}, {"limit": 2001}, {"from": "2100-01-01T00:00:00Z"}):
        assert client.get(path + "/readings", params=invalid).status_code == 422
    assert client.get(f"/api/v1/patients/{uuid4()}/readings").status_code == 404
