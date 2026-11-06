import asyncio
from uuid import uuid4

from alembic.runtime.migration import MigrationContext
from asyncpg import PostgresError
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models.health import HealthError, Readiness, Unready


def database_heads(connection: Connection) -> set[str]:
    return set(MigrationContext.configure(connection).get_current_heads())


async def check_readiness(engine: AsyncEngine, expected_heads: set[str]) -> Readiness | Unready:
    try:
        async with asyncio.timeout(3):
            async with engine.connect() as connection:
                heads = await connection.run_sync(database_heads)
        if heads == expected_heads:
            return Readiness()
        return Unready(
            database="available",
            migrations="pending",
            error=HealthError(code="migrations_pending", message="Database migrations are pending.", details={}),
            request_id=uuid4(),
        )
    except (OSError, PostgresError, SQLAlchemyError):
        return Unready(
            database="unavailable",
            migrations="unknown",
            error=HealthError(code="database_unavailable", message="PostgreSQL is unavailable.", details={}),
            request_id=uuid4(),
        )
