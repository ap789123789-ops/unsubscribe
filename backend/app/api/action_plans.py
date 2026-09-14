from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.actions.planner import ActionPlan, ActionPlanService, PlanSelection
from app.pipeline import StaleCandidate


class SelectionRequest(BaseModel):
    candidate_id: str
    revision: int = Field(ge=1)


class PlanCreateRequest(BaseModel):
    selections: list[SelectionRequest] = Field(min_length=1, max_length=500)


class PlanItemResponse(BaseModel):
    candidate_id: str
    revision: int
    sender: str
    subject: str
    method: str
    target_display: str


class ActionPlanResponse(BaseModel):
    id: str
    digest: str
    confirmed: bool
    items: list[PlanItemResponse]


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
            )
            for item in plan.items
        ],
    )


def create_action_plan_router(
    service: ActionPlanService,
    require_mutation: Callable[..., Awaitable[None]],
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
            plan = service.create(
                [PlanSelection(item.candidate_id, item.revision) for item in payload.selections]
            )
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
        except StaleCandidate as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The selection changed. Review the updated actions before unsubscribing.",
            ) from error
        return plan_response(plan)

    @router.get("/api/action-plans/{plan_id}", response_model=ActionPlanResponse)
    async def get_plan(plan_id: str) -> ActionPlanResponse:
        plan = service.get(plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return plan_response(plan)

    return router

