import httpx
import pytest

from app.domain.state_machine import ActionState
from app.executors.models import Rfc8058Payload
from app.executors.rfc8058 import (
    MAX_RESPONSE_BYTES,
    HttpResponse,
    HttpxRfcTransport,
    ResponseTooLarge,
    Rfc8058Executor,
)
from app.security.url_policy import ValidatedTarget


class CountingPolicy:
    def __init__(self) -> None:
        self.revalidations = 0

    async def revalidate_before_connect(self, target):
        self.revalidations += 1
        return target


class RecordingTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls = []

    async def post(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


async def test_rfc_executor_posts_exact_body_once_and_records_only_submitted() -> None:
    policy = CountingPolicy()
    transport = RecordingTransport(HttpResponse(status_code=204, body=b""))
    executor = Rfc8058Executor(policy=policy, transport=transport)
    target = ValidatedTarget(
        url="https://example.com/u?t=private",
        origin="https://example.com",
        hostname="example.com",
        addresses=("93.184.216.34",),
    )

    result = await executor.execute(Rfc8058Payload(target=target))

    assert result.state is ActionState.SUBMITTED
    assert policy.revalidations == 1
    assert len(transport.calls) == 1
    assert transport.calls[0]["body"] == b"List-Unsubscribe=One-Click"
    assert transport.calls[0]["follow_redirects"] is False
    assert transport.calls[0]["connect_ip"] == "93.184.216.34"
    assert transport.calls[0]["server_hostname"] == "example.com"
    assert transport.calls[0]["headers"] == {"Content-Type": "application/x-www-form-urlencoded"}


async def test_rfc_redirect_is_not_followed_or_claimed_complete() -> None:
    transport = RecordingTransport(
        HttpResponse(status_code=302, body=b"", location="https://other.example/u")
    )
    target = ValidatedTarget(
        url="https://example.com/u",
        origin="https://example.com",
        hostname="example.com",
        addresses=("93.184.216.34",),
    )

    result = await Rfc8058Executor(policy=CountingPolicy(), transport=transport).execute(
        Rfc8058Payload(target=target)
    )

    assert result.state is ActionState.NEEDS_USER
    assert result.evidence_code == "redirect_blocked"
    assert len(transport.calls) == 1


async def test_rfc_503_is_retryable_only_after_user_review() -> None:
    transport = RecordingTransport(HttpResponse(status_code=503, body=b"busy"))
    target = ValidatedTarget(
        url="https://example.com/u",
        origin="https://example.com",
        hostname="example.com",
        addresses=("93.184.216.34",),
    )

    result = await Rfc8058Executor(policy=CountingPolicy(), transport=transport).execute(
        Rfc8058Payload(target=target)
    )

    assert result.state is ActionState.FAILED
    assert result.retryable is True
    assert len(transport.calls) == 1


async def test_http_transport_caps_response_and_sends_no_ambient_credentials() -> None:
    seen: list[httpx.Request] = []

    def oversized(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))

    transport = HttpxRfcTransport(httpx.MockTransport(oversized))

    with pytest.raises(ResponseTooLarge):
        await transport.post(
            url="https://example.com/u",
            connect_ip="93.184.216.34",
            server_hostname="example.com",
            body=b"List-Unsubscribe=One-Click",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )

    assert len(seen) == 1
    assert seen[0].content == b"List-Unsubscribe=One-Click"
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "example.com"
    assert seen[0].extensions["sni_hostname"] == "example.com"
    assert "authorization" not in seen[0].headers
    assert "cookie" not in seen[0].headers
