"""Exercise the HTTP contract against a disposable database on the real Compose PostgreSQL."""

import asyncio
import os
from datetime import UTC, datetime
from collections.abc import Iterator
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import create_engine
from app.main import app


async def database_command(sql: str, params: dict | None = None):
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
            result = await connection.execute(text(sql), params or {})
            return result.scalar_one_or_none() if result.returns_rows else None
    finally:
        await engine.dispose()


@pytest.fixture
def client() -> Iterator[TestClient]:
    name = f"monitoring_test_{uuid4().hex}"
    asyncio.run(database_command(f"CREATE DATABASE {name}"))
    try:
        with pytest.MonkeyPatch.context() as env:
            env.setenv("POSTGRES_DB", name)
            config = Config("alembic.ini")
            command.upgrade(config, "head")
            with TestClient(app, headers={"X-Simulator-Key": os.environ["SIMULATOR_KEY"]}) as http:
                yield http
    finally:
        asyncio.run(database_command(f"DROP DATABASE {name}"))


def frame(sequence: int = 1) -> dict:
    return {
        "reading_id": str(uuid4()), "device_id": "30000000-0000-0000-0000-000000000001",
        "sequence": sequence, "observed_at": datetime.now(UTC).isoformat(),
        "heart_rate_bpm": 73, "spo2_pct": 99, "systolic_mmhg": 119, "diastolic_mmhg": 79,
        "temperature_c": 36.7,
    }
