import pytest

from app.gmail.oauth import InvalidOAuthState, OAuthCoordinator
from app.gmail.protocols import OAuthToken


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
    def authorization_url(self, *, state: str, code_challenge: str) -> str:
        return f"https://accounts.example/authorize?state={state}&challenge={code_challenge}"

    def exchange_code(self, *, code: str, code_verifier: str) -> OAuthToken:
        assert code == "authorization-code"
        assert len(code_verifier) >= 43
        return OAuthToken(serialized_credentials="secret-json", scopes=("gmail.readonly",))


def test_oauth_uses_pkce_and_persists_tokens_only_after_matching_state() -> None:
    credentials = MemoryCredentials()
    coordinator = OAuthCoordinator(FakeOAuthProvider(), credentials)

    start = coordinator.start()
    token = coordinator.complete(code="authorization-code", state=start.state)

    assert "challenge=" in start.authorization_url
    assert token.scopes == ("gmail.readonly",)
    assert credentials.values == {"google-oauth": "secret-json"}


def test_oauth_rejects_unknown_state_without_exchanging_or_storing() -> None:
    credentials = MemoryCredentials()
    coordinator = OAuthCoordinator(FakeOAuthProvider(), credentials)

    with pytest.raises(InvalidOAuthState):
        coordinator.complete(code="authorization-code", state="attacker-state")

    assert credentials.values == {}

