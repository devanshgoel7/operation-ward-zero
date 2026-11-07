from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from app.api.monitoring import ErrorEnvelope
from app.models.alerts import Acknowledge, Alert, AlertDetail, AlertPage, Resolve, Status
from app.services.alerts import acknowledge, alert_detail, list_alerts, resolve

router = APIRouter(prefix="/api/v1/alerts", responses={422: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}})


@router.get("")
async def alerts(request: Request, patient_id: UUID | None = None, assignee_id: UUID | None = None,
                 status: Status | None = None, cursor: str | None = None,
                 limit: Annotated[int, Query(ge=1, le=200)] = 50) -> AlertPage:
    async with request.app.state.engine.connect() as conn:
        return await list_alerts(conn, patient_id, assignee_id, status, cursor, limit)


@router.get("/{alert_id}", responses={404: {"model": ErrorEnvelope}})
async def detail(alert_id: UUID, request: Request) -> AlertDetail:
    async with request.app.state.engine.connect() as conn:
        return await alert_detail(conn, alert_id)


@router.post("/{alert_id}/acknowledge", responses={
    403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope},
})
async def acknowledge_alert(alert_id: UUID, body: Acknowledge, request: Request,
                            x_demo_caregiver_id: Annotated[UUID, Header()]) -> Alert:
    return await acknowledge(request.app.state.engine, alert_id, x_demo_caregiver_id, body.command_id,
                             hub=request.app.state.realtime)


@router.post("/{alert_id}/resolve", responses={
    403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope},
})
async def resolve_alert(alert_id: UUID, body: Resolve, request: Request,
                        x_demo_caregiver_id: Annotated[UUID, Header()]) -> Alert:
    return await resolve(request.app.state.engine, alert_id, x_demo_caregiver_id, body,
                         hub=request.app.state.realtime)
