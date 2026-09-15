from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.actions.coordinator import (
    ActionAlreadyAttempted,
    ExecutionCoordinator,
    ExecutionUnavailable,
)
from app.actions.planner import (
    ActionPlan,
    ActionPlanService,
    PlanDigestMismatch,
    PlanSelection,
)
from app.domain.models import ActionRecord, UnsubscribeMethod
from app.executors.mailto import SendAuthorizationRequired
from app.pipeline import StaleCandidate


class SelectionRequest(BaseModel):
    candidate_id: str
    revision: int = Field(ge=1)


class PlanCreateRequest(BaseModel):
    selections: list[SelectionRequest] = Field(min_length=1, max_length=500)


class PlanConfirmRequest(BaseModel):
    digest: str = Field(min_length=64, max_length=64)


class MailPreviewResponse(BaseModel):
    recipient: str
    subject: str
    body: str


class PlanItemResponse(BaseModel):
    candidate_id: str
    revision: int
    sender: str
    subject: str
    method: str
    target_display: str
    mail_preview: MailPreviewResponse | None = None


class ActionPlanResponse(BaseModel):
    id: str
    digest: str
    confirmed: bool
    items: list[PlanItemResponse]


class ActionResponse(BaseModel):
    id: str
    candidate_id: str
    method: str
    state: str
    browser_session_id: str | None = None


class ActionListResponse(BaseModel):
    items: list[ActionResponse]


def plan_response(plan: ActionPlan) -> ActionPlanResponse:
    return ActionPlanResponse(
        id=plan.id,
        digest=plan.digest,
        confirmed=plan.confirmed,
        items=[
            PlanItemResponse(
                candidate_id=item.candidate_id,
                revision=item.revision,
                sender=item.sender,
                subject=item.subject,
                method=item.method.value,
                target_display=item.target_display,
                mail_preview=(
                    MailPreviewResponse(
                        recipient=item.mail_draft.recipient,
                        subject=item.mail_draft.subject,
                        body=item.mail_draft.body,
                    )
                    if item.mail_draft is not None
                    else None
                ),
            )
            for item in plan.items
        ],
    )


def action_response(action: ActionRecord) -> ActionResponse:
    return ActionResponse(
        id=str(action.id),
        candidate_id=str(action.candidate_id),
        method=action.method.value,
        state=action.state.value,
        browser_session_id=(
            action.external_id if action.method is UnsubscribeMethod.BROWSER else None
        ),
    )


def create_action_plan_router(
    service: ActionPlanService,
    require_mutation: Callable[..., Awaitable[None]],
    coordinator: ExecutionCoordinator | None = None,
) -> APIRouter:
    router = APIRouter(tags=["action-plans"])

    @router.post(
        "/api/action-plans",
        response_model=ActionPlanResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_mutation)],
    )
    async def create_plan(payload: PlanCreateRequest) -> ActionPlanResponse:
        try:
            plan = await service.create(
                [PlanSelection(item.candidate_id, item.revision) for item in payload.selections]
            )
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
        except StaleCandidate as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The selection changed. Review the updated actions before unsubscribing.",
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
        return plan_response(plan)

    @router.get("/api/action-plans/{plan_id}", response_model=ActionPlanResponse)
    async def get_plan(plan_id: str) -> ActionPlanResponse:
        plan = service.get(plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return plan_response(plan)

    @router.post(
        "/api/action-plans/{plan_id}/confirm",
        response_model=ActionListResponse,
        dependencies=[Depends(require_mutation)],
    )
    async def confirm_plan(
        plan_id: str,
        payload: PlanConfirmRequest,
    ) -> ActionListResponse:
        if coordinator is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "execution_unavailable",
                    "message": "Secure action execution is not available on this system.",
                },
            )
        try:
            actions = await coordinator.confirm_and_execute(plan_id, payload.digest)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
        except (PlanDigestMismatch, StaleCandidate) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "stale_plan", "message": str(error)},
            ) from error
        except ActionAlreadyAttempted as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "action_already_attempted", "message": str(error)},
            ) from error
        except SendAuthorizationRequired as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "gmail_send_authorization_required",
                    "message": str(error),
                },
            ) from error
        except ExecutionUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "execution_unavailable", "message": str(error)},
            ) from error
        return ActionListResponse(items=[action_response(action) for action in actions])

    @router.get(
        "/api/action-plans/{plan_id}/actions",
        response_model=ActionListResponse,
    )
    async def list_plan_actions(plan_id: str) -> ActionListResponse:
        if coordinator is None:
            return ActionListResponse(items=[])
        actions = coordinator.actions_for_plan(plan_id)
        return ActionListResponse(items=[action_response(action) for action in actions])

    return router
