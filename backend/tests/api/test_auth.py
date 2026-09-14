from fastapi.testclient import TestClient

from app.gmail.oauth import OAuthCoordinator
from app.gmail.protocols import OAuthToken
from app.main import create_app


class MemoryCredentials:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


class FakeProvider:
    def authorization_url(self, *, state: str, code_challenge: str) -> str:
        return f"https://accounts.example/auth?state={state}&challenge={code_challenge}"

    def exchange_code(self, *, code: str, code_verifier: str) -> OAuthToken:
        return OAuthToken("stored-token", ("gmail.readonly",))


def test_oauth_api_requires_local_confirmation_and_supports_disconnect() -> None:
    credentials = MemoryCredentials()
    app = create_app(oauth_coordinator=OAuthCoordinator(FakeProvider(), credentials))
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    csrf = client.get("/api/session").json()["csrf_token"]
    mutation_headers = {
        "Origin": "http://127.0.0.1:8000",
        "X-CSRF-Token": csrf,
    }

    assert client.post("/auth/google/start").status_code == 403
    start = client.post("/auth/google/start", headers=mutation_headers)
    state = start.json()["state"]
    callback = client.get(
        "/auth/google/callback",
        params={"code": "code", "state": state},
    )

    assert callback.json() == {"connected": True, "scopes": ["gmail.readonly"]}
    assert credentials.get("google-oauth") == "stored-token"
    assert client.post("/api/accounts/disconnect", headers=mutation_headers).status_code == 204
    assert credentials.get("google-oauth") is None
