import json

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from app.persistence.repositories import ActionEventRecord, ActionRepository


def encode_event(event: ActionEventRecord) -> str:
    data = json.dumps(
        {
            "action_id": event.action_id,
            "state": event.state.value,
            "evidence_code": event.evidence_code,
            "safe_detail": event.safe_detail,
        },
        separators=(",", ":"),
    )
    return f"retry: 2000\nid: {event.id}\nevent: action-state\ndata: {data}\n\n"


def create_event_router(repository: ActionRepository | None) -> APIRouter:
    router = APIRouter(tags=["events"])

    @router.get(
        "/events/actions/{plan_id}",
        response_class=StreamingResponse,
        responses={
            200: {
                "description": "Replayable action-state event stream",
                "content": {"text/event-stream": {}},
            }
        },
    )
    async def action_events(
        plan_id: str,
        last_event_id: str | None = Header(
            default=None,
            alias="Last-Event-ID",
            min_length=1,
            max_length=100,
        ),
    ) -> StreamingResponse:
        if repository is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Action activity is unavailable",
            )
        try:
            events = repository.list_events(
                plan_id,
                after_event_id=last_event_id,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The event cursor is not part of this action plan",
            ) from error
        return StreamingResponse(
            iter(encode_event(event) for event in events),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store",
                "X-Accel-Buffering": "no",
            },
        )

    return router
