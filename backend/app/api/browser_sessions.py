from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.actions.browser_sessions import BrowserSessionService
from app.domain.models import ActionRecord
from app.executors.browser import BrowserSessionSnapshot


class BrowserSessionResponse(BaseModel):
    id: str
    action_id: str
    state: str
    blocker_code: str
    blocker_detail: str
    origin: str
    navigation_count: int
    blocked_request_count: int
    final_click_issued: bool
    manual_takeover: bool


class BrowserActionResponse(BaseModel):
    id: str
    state: str


def snapshot_response(snapshot: BrowserSessionSnapshot) -> BrowserSessionResponse:
    return BrowserSessionResponse(
        id=snapshot.id,
        action_id=snapshot.action_id,
        state=snapshot.state.value,
        blocker_code=snapshot.blocker_code,
        blocker_detail=snapshot.blocker_detail,
        origin=snapshot.origin,
        navigation_count=snapshot.navigation_count,
        blocked_request_count=snapshot.blocked_request_count,
        final_click_issued=snapshot.final_click_issued,
        manual_takeover=snapshot.manual_takeover,
    )


def action_response(action: ActionRecord) -> BrowserActionResponse:
    return BrowserActionResponse(id=str(action.id), state=action.state.value)


def create_browser_session_router(
    service: BrowserSessionService | None,
    require_mutation: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter(tags=["browser-sessions"])

    def configured() -> BrowserSessionService:
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Browser execution is unavailable",
            )
        return service

    @router.get(
        "/api/browser-sessions/{browser_session_id}",
        response_model=BrowserSessionResponse,
    )
    async def get_browser_session(browser_session_id: str) -> BrowserSessionResponse:
        try:
            return snapshot_response(configured().get(browser_session_id))
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error

    @router.post(
        "/api/browser-sessions/{browser_session_id}/take-over",
        response_model=BrowserSessionResponse,
        dependencies=[Depends(require_mutation)],
    )
    async def take_over_browser(browser_session_id: str) -> BrowserSessionResponse:
        try:
            return snapshot_response(await configured().take_over(browser_session_id))
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error

    @router.post(
        "/api/browser-sessions/{browser_session_id}/resume",
        response_model=BrowserActionResponse,
        dependencies=[Depends(require_mutation)],
    )
    async def resume_browser(browser_session_id: str) -> BrowserActionResponse:
        try:
            return action_response(await configured().resume(browser_session_id))
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error

    @router.post(
        "/api/browser-sessions/{browser_session_id}/cancel",
        response_model=BrowserActionResponse,
        dependencies=[Depends(require_mutation)],
    )
    async def cancel_browser(browser_session_id: str) -> BrowserActionResponse:
        try:
            return action_response(await configured().cancel(browser_session_id))
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error

    return router
