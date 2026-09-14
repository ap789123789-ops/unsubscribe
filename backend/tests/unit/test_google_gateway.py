import json

from app.gmail.google_gateway import GoogleGmailGateway, GoogleOAuthProvider


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
