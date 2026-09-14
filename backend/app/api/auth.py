from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.gmail.oauth import InvalidOAuthState, OAuthCoordinator
from app.gmail.protocols import OAuthIntent


class OAuthStartResponse(BaseModel):
    state: str
    authorization_url: str


class AccountResponse(BaseModel):
    connected: bool
    scopes: list[str]


def create_auth_router(
    coordinator: OAuthCoordinator | None,
    require_mutation: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter(tags=["gmail-auth"])

    def configured() -> OAuthCoordinator:
        if coordinator is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google OAuth is not configured",
            )
        return coordinator

    @router.post(
        "/auth/google/start",
        response_model=OAuthStartResponse,
        dependencies=[Depends(require_mutation)],
    )
    async def start_google_oauth(
        intent: OAuthIntent = OAuthIntent.READ,
        return_to: str = "/review",
    ) -> OAuthStartResponse:
        try:
            start = configured().start(intent, return_to=return_to)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return OAuthStartResponse(
            state=start.state,
            authorization_url=start.authorization_url,
        )

    @router.get("/auth/google/callback", response_class=RedirectResponse)
    async def finish_google_oauth(code: str, state: str) -> RedirectResponse:
        try:
            completion = configured().complete(code=code, state=state)
        except InvalidOAuthState as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        separator = "&" if "?" in completion.return_to else "?"
        return RedirectResponse(
            f"{completion.return_to}{separator}gmail=connected",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @router.get("/api/account", response_model=AccountResponse)
    async def account_status() -> AccountResponse:
        active = configured()
        return AccountResponse(
            connected=active.is_connected(),
            scopes=list(active.current_scopes()),
        )

    @router.post(
        "/api/accounts/disconnect",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_mutation)],
    )
    async def disconnect_google() -> Response:
        configured().disconnect()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
