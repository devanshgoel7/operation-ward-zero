from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.database import create_engine
from app.api.health import router as health_router

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
app.include_router(health_router)
app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="shell")
