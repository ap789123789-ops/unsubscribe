import base64
import json
from email import message_from_bytes

import httpx

from app.actions.planner import ExactMailDraft
from app.gmail.google_gateway import (
    GoogleGmailGateway,
    GoogleOAuthProvider,
    StoredCredentialGmailGateway,
)
from app.gmail.protocols import OAuthIntent


class Request:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response

    def execute(self) -> dict[str, object]:
        return self.response


class MessagesResource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list(self, **kwargs: object) -> Request:
        self.calls.append(("list", kwargs))
        return Request(
            {
                "messages": [{"id": "m1", "threadId": "t1"}],
                "nextPageToken": "next",
            }
        )

    def get(self, **kwargs: object) -> Request:
        self.calls.append(("get", kwargs))
        return Request(
            {
                "id": "m1",
                "threadId": "t1",
                "sizeEstimate": 321,
                "internalDate": "1700000000000",
                "payload": {"headers": []},
            }
        )

    def send(self, **kwargs: object) -> Request:
        self.calls.append(("send", kwargs))
        return Request({"id": "sent-1"})


class UsersResource:
    def __init__(self, messages: MessagesResource) -> None:
        self._messages = messages

    def messages(self) -> MessagesResource:
        return self._messages

    def getProfile(self, **kwargs: object) -> Request:  # noqa: N802 - Google SDK shape
        return Request({"emailAddress": "reader@example.com"})


class GmailService:
    def __init__(self) -> None:
        self.messages_resource = MessagesResource()

    def users(self) -> UsersResource:
        return UsersResource(self.messages_resource)


async def test_google_gateway_lists_refs_then_fetches_full_message() -> None:
    service = GmailService()
    credentials_json = json.dumps(
        {
            "token": "access",
            "refresh_token": "refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client",
            "client_secret": "secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }
    )
    gateway = GoogleGmailGateway(credentials_json, service_factory=lambda _: service)

    page = await gateway.list_messages(query="newer_than:30d", max_results=100, page_token=None)
    message = await gateway.get_message("m1")

    assert page.messages[0].id == "m1"
    assert page.next_page_token == "next"
    assert message.size_estimate == 321
    assert service.messages_resource.calls == [
        (
            "list",
            {
                "userId": "me",
                "q": "newer_than:30d",
                "maxResults": 100,
                "includeSpamTrash": False,
            },
        ),
        ("get", {"userId": "me", "id": "m1", "format": "full"}),
    ]


def test_oauth_provider_builds_loopback_pkce_url(tmp_path) -> None:
    client_file = tmp_path / "credentials.json"
    client_file.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client.apps.googleusercontent.com",
                    "project_id": "project",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_secret": "secret",
                    "redirect_uris": ["http://localhost"],
                }
            }
        )
    )
    provider = GoogleOAuthProvider(
        client_secrets_file=client_file,
        redirect_uri="http://127.0.0.1:8000/auth/google/callback",
    )

    url = provider.authorization_url(state="state-1", code_challenge="challenge-1")

    assert "state=state-1" in url
    assert "code_challenge=challenge-1" in url
    assert "code_challenge_method=S256" in url
    assert "gmail.readonly" in url

    send_url = provider.authorization_url(
        state="state-2",
        code_challenge="challenge-2",
        intent=OAuthIntent.SEND,
    )
    assert "gmail.readonly" in send_url
    assert "gmail.send" in send_url


def test_oauth_provider_revokes_refresh_token_without_following_redirects(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def revoke(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    provider = GoogleOAuthProvider(
        client_secrets_file=tmp_path / "unused.json",
        redirect_uri="http://127.0.0.1:8000/auth/google/callback",
        revoke_transport=httpx.MockTransport(revoke),
    )
    serialized = json.dumps({"token": "access-secret", "refresh_token": "refresh-secret"})

    assert provider.revoke(serialized) is True
    assert len(requests) == 1
    assert requests[0].url == "https://oauth2.googleapis.com/revoke"
    assert requests[0].content == b"token=refresh-secret"


async def test_google_gateway_sends_exact_message_and_reconciles_sent_mail() -> None:
    service = GmailService()
    credentials_json = json.dumps(
        {
            "token": "access",
            "refresh_token": "refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client",
            "client_secret": "secret",
            "scopes": [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
            ],
        }
    )
    gateway = GoogleGmailGateway(credentials_json, service_factory=lambda _: service)
    draft = ExactMailDraft("leave@example.com", "Remove me", "Please unsubscribe me")
    message_id = "<unsubscribe-opaque@local.invalid>"

    sent_id = await gateway.send_mailto_unsubscribe(draft, message_id)
    found_id = await gateway.find_sent_by_message_id(message_id)

    assert await gateway.has_send_scope() is True
    assert sent_id == "sent-1"
    assert found_id == "m1"
    send_call = service.messages_resource.calls[0]
    raw = send_call[1]["body"]["raw"]  # type: ignore[index]
    decoded = message_from_bytes(base64.urlsafe_b64decode(raw))
    assert decoded["To"] == "leave@example.com"
    assert decoded["Subject"] == "Remove me"
    assert decoded["Message-ID"] == message_id
    assert decoded.get_payload().strip() == "Please unsubscribe me"
    assert service.messages_resource.calls[1] == (
        "list",
        {
            "userId": "me",
            "q": f"in:sent rfc822msgid:{message_id}",
            "maxResults": 1,
            "includeSpamTrash": False,
        },
    )


async def test_stored_gateway_reports_no_send_scope_before_connection() -> None:
    class EmptyStore:
        def get(self, key: str) -> str | None:
            return None

        def set(self, key: str, value: str) -> None:
            pass

        def delete(self, key: str) -> None:
            pass

    assert await StoredCredentialGmailGateway(EmptyStore()).has_send_scope() is False
