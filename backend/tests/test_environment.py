"""Run in the started M0 app container against its real PostgreSQL service."""

from pathlib import Path

import httpx
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.main import app

BASE = "http://127.0.0.1:8000"


def test_import_and_migration_head() -> None:
    assert app.title == "Operation Ward Zero"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    assert ScriptDirectory.from_config(config).get_current_head() is not None


def test_health_responses() -> None:
    with httpx.Client(base_url=BASE) as client:
        live = client.get("/health/live")
        assert live.status_code == 200
        assert live.json() == {"status": "live"}
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json() == {
            "status": "ready",
            "database": "available",
            "migrations": "current",
            "worker_last_success_at": None,
        }


def test_published_contract() -> None:
    response = httpx.get(f"{BASE}/openapi.json")
    response.raise_for_status()
    paths = response.json()["paths"]
    assert "200" in paths["/health/live"]["get"]["responses"]
    assert {"200", "503"} <= paths["/health/ready"]["get"]["responses"].keys()
