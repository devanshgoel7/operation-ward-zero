import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from app.db import create_engine


def migrate(connection: Connection) -> None:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


asyncio.run(run())
