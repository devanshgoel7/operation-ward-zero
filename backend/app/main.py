import asyncio
import logging
from datetime import UTC, datetime
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.database import create_engine
from app.services.alerts import escalate_due
from app.services.quality import check_freshness
from sqlalchemy.exc import SQLAlchemyError
from asyncpg import PostgresError
from app.api.health import router as health_router
from app.api.monitoring import handlers, router as monitoring_router
from app.api.alerts import router as alerts_router

ROOT = Path(__file__).resolve().parents[1]


async def run_checks(app: FastAPI) -> None:
    await check_freshness(app.state.engine, datetime.now(UTC))
    await escalate_due(app.state.engine)
    app.state.worker_last_success_at = datetime.now(UTC)


async def periodic_checks(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(5)
        try:
            await run_checks(app)
        except (SQLAlchemyError, PostgresError, OSError):
            logging.exception("Could not check freshness and deadlines; retrying in five seconds.")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.engine = create_engine()
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    app.state.expected_heads = set(scripts.get_heads())
    await run_checks(app)
    worker = asyncio.create_task(periodic_checks(app))
    try:
        yield
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await app.state.engine.dispose()


app = FastAPI(title="Operation Ward Zero", version="0.3.0", lifespan=lifespan, exception_handlers=handlers)
app.include_router(health_router)
app.include_router(monitoring_router)
app.include_router(alerts_router)
app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="shell")
