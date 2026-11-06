import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from asyncpg import PostgresError
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.models.monitoring import Caregiver, Dashboard, PatientSnapshot, ReadingInput, ReadingPage, Receipt
from app.services.alerts import list_alerts
from app.services.errors import MonitoringError
from app.services.monitoring import history, ingest, snapshots


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: dict[str, str]


class ErrorEnvelope(BaseModel):
    error: ErrorInfo
    request_id: UUID


def error_response(status: int, code: str, message: str, details: dict[str, str]) -> JSONResponse:
    body = ErrorEnvelope(error=ErrorInfo(code=code, message=message, details=details), request_id=uuid4())
    return JSONResponse(body.model_dump(mode="json"), status_code=status)


async def monitoring_error(request: Request, exc: MonitoringError) -> JSONResponse:
    return error_response(exc.status, exc.code, str(exc), {})


async def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = {".".join(map(str, item["loc"])): item["msg"] for item in exc.errors()}
    return error_response(422, "invalid_input", "Check the request fields.", fields)


async def unavailable(request: Request, exc: Exception) -> JSONResponse:
    return error_response(503, "database_unavailable", "Could not complete the database request.", {})


handlers = {MonitoringError: monitoring_error, RequestValidationError: invalid_input,
            SQLAlchemyError: unavailable, PostgresError: unavailable, OSError: unavailable}
router = APIRouter(prefix="/api/v1", responses={422: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}})
key_header = APIKeyHeader(name="X-Simulator-Key", auto_error=False)


def authenticate(key: Annotated[str | None, Depends(key_header)]) -> None:
    if not secrets.compare_digest((key or "").encode(), os.environ["SIMULATOR_KEY"].encode()):
        raise MonitoringError(403, "invalid_key", "Sensor key required.")


@router.post("/readings", status_code=201, dependencies=[Depends(authenticate)],
             responses={200: {"model": Receipt}, 403: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}})
async def post_reading(reading: ReadingInput, request: Request, response: Response) -> Receipt:
    receipt = await ingest(request.app.state.engine, reading)
    if receipt.disposition == "duplicate":
        response.status_code = 200
    return receipt


@router.get("/dashboard")
async def dashboard(request: Request) -> Dashboard:
    async with request.app.state.engine.connect() as conn:
        caregivers = await conn.execute(text("SELECT id, display_name FROM caregivers ORDER BY id"))
        return Dashboard(server_time=datetime.now(UTC), patients=await snapshots(conn),
                         active_alerts=(await list_alerts(conn)).items,
                         caregivers=[Caregiver.model_validate(row) for row in caregivers.mappings()])


@router.get("/patients/{patient_id}", responses={404: {"model": ErrorEnvelope}})
async def patient(patient_id: UUID, request: Request) -> PatientSnapshot:
    async with request.app.state.engine.connect() as conn:
        rows = await snapshots(conn, patient_id)
        if not rows:
            raise MonitoringError(404, "unknown_patient", "Patient does not exist.")
        return rows[0]


@router.get("/patients/{patient_id}/readings", responses={404: {"model": ErrorEnvelope}})
async def patient_readings(patient_id: UUID, request: Request,
                           start: Annotated[AwareDatetime | None, Query(alias="from")] = None,
                           end: Annotated[AwareDatetime | None, Query(alias="to")] = None,
                           cursor: str | None = None,
                           limit: Annotated[int, Query(ge=1, le=2000)] = 500) -> ReadingPage:
    end = end or datetime.now(UTC)
    start = start or end - timedelta(minutes=30)
    if start > end:
        raise MonitoringError(422, "invalid_range", "Start must be at or before end.")
    async with request.app.state.engine.connect() as conn:
        if not await conn.scalar(text("SELECT 1 FROM patients WHERE id = :id"), {"id": patient_id}):
            raise MonitoringError(404, "unknown_patient", "Patient does not exist.")
        return await history(conn, patient_id, start, end, cursor, limit)
