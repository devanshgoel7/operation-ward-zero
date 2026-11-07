from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response

from app.api.monitoring import ErrorEnvelope
from app.models.alerts import ObservationReceipt
from app.models.observations import ObservationInput
from app.services.observations import record_observation

router = APIRouter(prefix="/api/v1", responses={
    code: {"model": ErrorEnvelope} for code in (403, 404, 409, 422, 503)
})


@router.post("/patients/{patient_id}/observations", status_code=201, responses={200: {"model": ObservationReceipt}})
async def post_observation(patient_id: UUID, body: ObservationInput, request: Request, response: Response,
                           x_demo_caregiver_id: Annotated[UUID, Header()]) -> ObservationReceipt:
    receipt, replay = await record_observation(request.app.state.engine, patient_id, x_demo_caregiver_id, body)
    if replay:
        response.status_code = 200
    return receipt
