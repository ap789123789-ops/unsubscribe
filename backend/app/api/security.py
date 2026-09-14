import hmac
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel

SESSION_COOKIE = "unsubscribe_session"


@dataclass
class SessionRegistry:
    sessions: dict[str, str] = field(default_factory=dict)

    def issue(self) -> tuple[str, str]:
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        self.sessions[session_id] = csrf_token
        return session_id, csrf_token

    def valid(self, session_id: str | None, csrf_token: str | None) -> bool:
        if not session_id or not csrf_token:
            return False
        expected = self.sessions.get(session_id)
        return expected is not None and hmac.compare_digest(expected, csrf_token)


class SessionResponse(BaseModel):
    csrf_token: str


class VerificationResponse(BaseModel):
    verified: bool = True


@dataclass(frozen=True)
class LocalSecurity:
    router: APIRouter
    require_mutation: Callable[..., Awaitable[None]]


def create_local_security(
    registry: SessionRegistry,
    allowed_origins: frozenset[str],
) -> LocalSecurity:
    router = APIRouter(tags=["security"])

    @router.get("/api/session", response_model=SessionResponse)
    async def create_session(response: Response) -> SessionResponse:
        session_id, csrf_token = registry.issue()
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            httponly=True,
            samesite="strict",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        return SessionResponse(csrf_token=csrf_token)

    async def require_local_mutation(
        request: Request,
        session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> None:
        origin = request.headers.get("origin")
        if origin not in allowed_origins or not registry.valid(session_id, csrf_token):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Mutation rejected")

    @router.post(
        "/api/session/verify",
        response_model=VerificationResponse,
        dependencies=[Depends(require_local_mutation)],
    )
    async def verify_session() -> VerificationResponse:
        return VerificationResponse()

    return LocalSecurity(router=router, require_mutation=require_local_mutation)
