from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.models.health import Liveness, Readiness, Unready
from app.services.health import check_readiness

router = APIRouter(prefix="/health")


@router.get("/live")
def live() -> Liveness:
    return Liveness()


@router.get("/ready", response_model=Readiness, responses={503: {"model": Unready}})
async def ready(request: Request) -> Readiness | JSONResponse:
    result = await check_readiness(request.app.state.engine, request.app.state.expected_heads)
    if isinstance(result, Unready):
        return JSONResponse(status_code=503, content=result.model_dump(mode="json"))
    return result
