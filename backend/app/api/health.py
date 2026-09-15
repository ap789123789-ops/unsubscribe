from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, status

from app.api.schemas import HealthResponse


@dataclass
class Readiness:
    ready: bool = False


def create_health_router(readiness: Readiness) -> APIRouter:
    router = APIRouter(tags=["system"])

    @router.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        if not readiness.ready:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Startup recovery is still running",
            )
        return HealthResponse()

    return router
