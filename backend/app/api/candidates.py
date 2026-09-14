from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.candidates.grouper import SubscriptionCandidate
from app.domain.models import ClassificationCategory
from app.pipeline import InMemoryCandidateCatalog, StaleCandidate


class CandidateResponse(BaseModel):
    id: str
    revision: int
    sender: str
    representative_subject: str
    message_count: int
    category: ClassificationCategory
    confidence: float
    reason: str
    evidence_quote: str
    method: str
    target_display: str
    first_seen: str
    last_seen: str


class CandidateListResponse(BaseModel):
    items: list[CandidateResponse]


class CandidateCorrectionRequest(BaseModel):
    category: ClassificationCategory
    expected_revision: int


def candidate_response(candidate: SubscriptionCandidate) -> CandidateResponse:
    from app.actions.planner import display_target

    return CandidateResponse(
        id=candidate.id,
        revision=candidate.revision,
        sender=candidate.sender,
        representative_subject=candidate.representative_subject,
        message_count=len(candidate.message_ids),
        category=candidate.category,
        confidence=candidate.confidence,
        reason=candidate.reason,
        evidence_quote=candidate.evidence_quote,
        method=candidate.method.method.value,
        target_display=display_target(candidate.method.method, candidate.method.target),
        first_seen=candidate.first_seen.isoformat(),
        last_seen=candidate.last_seen.isoformat(),
    )


def create_candidate_router(
    catalog: InMemoryCandidateCatalog,
    require_mutation: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter(tags=["candidates"])

    @router.get("/api/candidates", response_model=CandidateListResponse)
    async def list_candidates() -> CandidateListResponse:
        return CandidateListResponse(
            items=[candidate_response(item) for item in catalog.candidates()]
        )

    @router.patch(
        "/api/candidates/{candidate_id}",
        response_model=CandidateResponse,
        dependencies=[Depends(require_mutation)],
    )
    async def correct_candidate(
        candidate_id: str,
        payload: CandidateCorrectionRequest,
    ) -> CandidateResponse:
        try:
            corrected = catalog.correct(
                candidate_id,
                payload.expected_revision,
                payload.category,
            )
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
        except StaleCandidate as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Candidate changed; review it again",
            ) from error
        return candidate_response(corrected)

    return router
