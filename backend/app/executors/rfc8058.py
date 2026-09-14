from dataclasses import dataclass
from typing import Protocol

import httpx

from app.domain.state_machine import ActionState
from app.executors.models import ExecutionResult, Rfc8058Payload
from app.security.url_policy import UnsafeTarget, UrlSafetyPolicy

RFC8058_BODY = b"List-Unsubscribe=One-Click"
MAX_RESPONSE_BYTES = 64 * 1024


class ResponseTooLarge(RuntimeError):
    pass


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: bytes
    location: str | None = None


class RfcTransport(Protocol):
    async def post(
        self,
        *,
        url: str,
        body: bytes,
        headers: dict[str, str],
        follow_redirects: bool,
    ) -> HttpResponse: ...


class HttpxRfcTransport:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def post(
        self,
        *,
        url: str,
        body: bytes,
        headers: dict[str, str],
        follow_redirects: bool,
    ) -> HttpResponse:
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=follow_redirects,
            trust_env=False,
            transport=self._transport,
        ) as client, client.stream(
            "POST", url, content=body, headers=headers
        ) as response:
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ResponseTooLarge("Unsubscribe response exceeded the safety limit")
                chunks.append(chunk)
            return HttpResponse(
                status_code=response.status_code,
                body=b"".join(chunks),
                location=response.headers.get("location"),
            )


class Rfc8058Executor:
    def __init__(self, *, policy: UrlSafetyPolicy, transport: RfcTransport) -> None:
        self._policy = policy
        self._transport = transport

    async def execute(self, payload: Rfc8058Payload) -> ExecutionResult:
        try:
            target = await self._policy.revalidate_before_connect(payload.target)
        except UnsafeTarget:
            return ExecutionResult(
                state=ActionState.FAILED,
                evidence_code="target_revalidation_failed",
                safe_detail="The destination failed its final public-network safety check.",
            )
        try:
            response = await self._transport.post(
                url=target.url,
                body=RFC8058_BODY,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                follow_redirects=False,
            )
        except (httpx.RequestError, ResponseTooLarge, TimeoutError):
            return ExecutionResult(
                state=ActionState.NEEDS_USER,
                evidence_code="submission_uncertain",
                safe_detail="The request outcome is uncertain; it was not repeated.",
            )

        if 200 <= response.status_code < 300:
            return ExecutionResult(
                state=ActionState.SUBMITTED,
                evidence_code="rfc8058_request_accepted",
                safe_detail="The one-click request was accepted; list processing is not verified.",
            )
        if 300 <= response.status_code < 400:
            return ExecutionResult(
                state=ActionState.NEEDS_USER,
                evidence_code="redirect_blocked",
                safe_detail="The destination tried to redirect; no redirect was followed.",
            )
        retryable = response.status_code in {429, 503}
        return ExecutionResult(
            state=ActionState.FAILED,
            evidence_code=f"http_{response.status_code}",
            safe_detail=(
                "The server rejected the request. A reviewed retry may be available."
                if retryable
                else "The server rejected the request."
            ),
            retryable=retryable,
        )
