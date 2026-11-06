from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


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
