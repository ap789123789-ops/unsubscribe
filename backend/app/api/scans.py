import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.observability import safe_exception_stack
from app.scan.service import ScanFailure, ScanRequest, ScanService

logger = logging.getLogger(__name__)


class ScanCreateRequest(BaseModel):
    scan_id: str = Field(min_length=1, max_length=100)
    days: int = Field(default=30, ge=1, le=365)
    max_messages: int = Field(default=500, ge=1, le=500)


class ScanResponse(BaseModel):
    scan_id: str
    processed_count: int
    completed: bool


def create_scan_router(
    service: ScanService | None,
    require_mutation: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter(tags=["scans"])

    @router.post(
        "/api/scans",
        response_model=ScanResponse,
        dependencies=[Depends(require_mutation)],
    )
    async def run_scan(payload: ScanCreateRequest) -> ScanResponse:
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Connect Gmail before starting a scan",
            )
        try:
            result = await service.run(
                ScanRequest(
                    scan_id=payload.scan_id,
                    days=payload.days,
                    max_messages=payload.max_messages,
                )
            )
        except ScanFailure as error:
            cause = error.__cause__ or error
            logger.error(
                "scan_failed scan_id=%r code=%s cause=%s stack=%s",
                payload.scan_id,
                error.code,
                type(cause).__name__,
                safe_exception_stack(cause),
            )
            if error.code == "gmail_access_unavailable":
                error_status = status.HTTP_502_BAD_GATEWAY
                message = "Gmail could not be read. Reconnect Gmail, then retry the scan."
            else:
                error_status = status.HTTP_500_INTERNAL_SERVER_ERROR
                message = "One email could not be processed. Progress was saved; retry the scan."
            raise HTTPException(
                status_code=error_status,
                detail={
                    "code": error.code,
                    "message": message,
                    "scan_id": payload.scan_id,
                },
            ) from error
        return ScanResponse(
            scan_id=result.scan_id,
            processed_count=result.processed_count,
            completed=result.completed,
        )

    return router
