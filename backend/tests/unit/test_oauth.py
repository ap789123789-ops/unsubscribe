import pytest

from app.gmail.oauth import InvalidOAuthState, OAuthCoordinator
from app.gmail.protocols import OAuthIntent, OAuthToken


class MemoryCredentials:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


class FakeOAuthProvider:
    def __init__(self, *, revoke_result: bool = True) -> None:
        self.revoke_result = revoke_result
        self.revoked: list[str] = []

    def authorization_url(self, *, state: str, code_challenge: str, intent: OAuthIntent) -> str:
        return f"https://accounts.example/authorize?state={state}&challenge={code_challenge}"

    def exchange_code(self, *, code: str, code_verifier: str, intent: OAuthIntent) -> OAuthToken:
        assert code == "authorization-code"
        assert len(code_verifier) >= 43
        return OAuthToken(serialized_credentials="secret-json", scopes=("gmail.readonly",))

    def revoke(self, serialized_credentials: str) -> bool:
        self.revoked.append(serialized_credentials)
        return self.revoke_result


def test_oauth_uses_pkce_and_persists_tokens_only_after_matching_state() -> None:
    credentials = MemoryCredentials()
    coordinator = OAuthCoordinator(FakeOAuthProvider(), credentials)

    start = coordinator.start()
    completion = coordinator.complete(code="authorization-code", state=start.state)

    assert "challenge=" in start.authorization_url
    assert completion.token.scopes == ("gmail.readonly",)
    assert completion.return_to == "/review"
    assert credentials.values == {
        "google-oauth": "secret-json",
        "google-oauth-scopes": '["gmail.readonly"]',
    }


def test_oauth_rejects_unknown_state_without_exchanging_or_storing() -> None:
    credentials = MemoryCredentials()
    coordinator = OAuthCoordinator(FakeOAuthProvider(), credentials)

    with pytest.raises(InvalidOAuthState):
        coordinator.complete(code="authorization-code", state="attacker-state")

    assert credentials.values == {}


def test_oauth_rejects_external_return_path() -> None:
    coordinator = OAuthCoordinator(FakeOAuthProvider(), MemoryCredentials())

    with pytest.raises(ValueError, match="local"):
        coordinator.start(return_to="//attacker.example/steal")


def test_disconnect_revokes_google_access_then_clears_local_credentials() -> None:
    credentials = MemoryCredentials()
    provider = FakeOAuthProvider()
    coordinator = OAuthCoordinator(provider, credentials)
    credentials.set(coordinator.credential_key, "secret-json")
    credentials.set(coordinator.scopes_key, '["gmail.readonly"]')

    assert coordinator.disconnect() is True
    assert provider.revoked == ["secret-json"]
    assert credentials.values == {}


def test_disconnect_clears_local_credentials_when_revocation_fails() -> None:
    credentials = MemoryCredentials()
    provider = FakeOAuthProvider(revoke_result=False)
    coordinator = OAuthCoordinator(provider, credentials)
    credentials.set(coordinator.credential_key, "secret-json")
    credentials.set(coordinator.scopes_key, '["gmail.readonly"]')

    assert coordinator.disconnect() is False
    assert credentials.values == {}
