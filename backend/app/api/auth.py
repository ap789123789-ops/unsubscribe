from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.gmail.oauth import InvalidOAuthState, OAuthCoordinator


class OAuthStartResponse(BaseModel):
    state: str
    authorization_url: str


class OAuthCompleteResponse(BaseModel):
    connected: bool = True
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
    async def start_google_oauth() -> OAuthStartResponse:
        start = configured().start()
        return OAuthStartResponse(
            state=start.state,
            authorization_url=start.authorization_url,
        )

    @router.get("/auth/google/callback", response_model=OAuthCompleteResponse)
    async def finish_google_oauth(code: str, state: str) -> OAuthCompleteResponse:
        try:
            token = configured().complete(code=code, state=state)
        except InvalidOAuthState as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return OAuthCompleteResponse(scopes=list(token.scopes))

    @router.post(
        "/api/accounts/disconnect",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_mutation)],
    )
    async def disconnect_google() -> Response:
        configured().disconnect()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
