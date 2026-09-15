from collections.abc import Awaitable, Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.actions.coordinator import (
    ActionRetryNotAllowed,
    ExecutionCoordinator,
    ExecutionUnavailable,
)
from app.domain.models import UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.persistence.repositories import ActionRepository, ActivityRecord


class ActivityActionResponse(BaseModel):
    id: str
    plan_id: str
    candidate_id: str
    sender: str
    subject: str
    target_display: str
    method: str
    state: str
    evidence_code: str | None
    safe_detail: str | None
    updated_at: datetime
    retry_available: bool
    browser_session_id: str | None


class ActivityActionListResponse(BaseModel):
    items: list[ActivityActionResponse]


def activity_response(record: ActivityRecord) -> ActivityActionResponse:
    action = record.action
    rfc_retry = (
        action.method is UnsubscribeMethod.RFC8058
        and action.state is ActionState.FAILED
        and record.evidence_code in {"http_429", "http_503"}
    )
    mailto_retry = (
        action.method is UnsubscribeMethod.MAILTO
        and action.state is ActionState.NEEDS_USER
        and record.evidence_code == "gmail_send_authorization_required"
    )
    retry_available = action.retry_count == 0 and (rfc_retry or mailto_retry)
    return ActivityActionResponse(
        id=str(action.id),
        plan_id=str(action.plan_id),
        candidate_id=str(action.candidate_id),
        sender=action.display_sender,
        subject=action.display_subject,
        target_display=action.target_display,
        method=action.method.value,
        state=action.state.value,
        evidence_code=record.evidence_code,
        safe_detail=record.safe_detail,
        updated_at=action.updated_at,
        retry_available=retry_available,
        browser_session_id=(
            action.external_id
            if action.method is UnsubscribeMethod.BROWSER and action.state is ActionState.NEEDS_USER
            else None
        ),
    )


def create_activity_router(
    repository: ActionRepository,
    require_mutation: Callable[..., Awaitable[None]],
    coordinator: ExecutionCoordinator | None = None,
) -> APIRouter:
    router = APIRouter(tags=["activity"])

    @router.get("/api/actions", response_model=ActivityActionListResponse)
    async def list_activity(
        plan_id: str | None = Query(default=None, max_length=36),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> ActivityActionListResponse:
        records = repository.list_activity(plan_id=plan_id, limit=limit)
        return ActivityActionListResponse(items=[activity_response(item) for item in records])

    @router.post(
        "/api/actions/{action_id}/retry",
        response_model=ActivityActionResponse,
        dependencies=[Depends(require_mutation)],
    )
    async def retry_activity(action_id: str) -> ActivityActionResponse:
        if coordinator is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "execution_unavailable",
                    "message": "Action repair is unavailable.",
                },
            )
        try:
            await coordinator.review_and_retry(action_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
        except ActionRetryNotAllowed as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "retry_not_allowed", "message": str(error)},
            ) from error
        except ExecutionUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "execution_unavailable", "message": str(error)},
            ) from error
        activity = repository.get_activity(action_id)
        assert activity is not None
        return activity_response(activity)

    return router
