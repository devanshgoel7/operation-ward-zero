import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from asyncpg import PostgresError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.db import create_engine

ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.engine = create_engine()
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    app.state.expected_heads = set(scripts.get_heads())
    try:
        yield
    finally:
        await app.state.engine.dispose()


app = FastAPI(title="Operation Ward Zero", version="0.1.0", lifespan=lifespan)


class Liveness(BaseModel):
    status: Literal["live"] = "live"


class Readiness(BaseModel):
    status: Literal["ready"] = "ready"
    database: Literal["available"] = "available"
    migrations: Literal["current"] = "current"
    worker_last_success_at: datetime | None = None


class HealthError(BaseModel):
    code: Literal["database_unavailable", "migrations_pending"]
    message: str
    details: dict[str, str]


class Unready(BaseModel):
    status: Literal["unready"] = "unready"
    database: Literal["available", "unavailable"]
    migrations: Literal["pending", "unknown"]
    worker_last_success_at: datetime | None = None
    error: HealthError
    request_id: UUID


@app.get("/health/live")
def live() -> Liveness:
    return Liveness()


def database_heads(connection: Connection) -> set[str]:
    return set(MigrationContext.configure(connection).get_current_heads())


@app.get("/health/ready", response_model=Readiness, responses={503: {"model": Unready}})
async def ready(request: Request) -> Readiness | JSONResponse:
    try:
        async with asyncio.timeout(3):
            async with request.app.state.engine.connect() as connection:
                heads = await connection.run_sync(database_heads)
        if heads == request.app.state.expected_heads:
            return Readiness()
        result = Unready(
            database="available",
            migrations="pending",
            error=HealthError(code="migrations_pending", message="Database migrations are pending.", details={}),
            request_id=uuid4(),
        )
    except (OSError, PostgresError, SQLAlchemyError):
        result = Unready(
            database="unavailable",
            migrations="unknown",
            error=HealthError(code="database_unavailable", message="PostgreSQL is unavailable.", details={}),
            request_id=uuid4(),
        )
    return JSONResponse(status_code=503, content=result.model_dump(mode="json"))


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="shell")
