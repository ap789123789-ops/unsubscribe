import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.gmail.protocols import CredentialStore, OAuthIntent, OAuthProvider, OAuthToken


class InvalidOAuthState(ValueError):
    pass


@dataclass(frozen=True)
class OAuthStart:
    state: str
    authorization_url: str


@dataclass(frozen=True)
class OAuthCompletion:
    token: OAuthToken
    return_to: str


@dataclass(frozen=True)
class PendingOAuth:
    verifier: str
    intent: OAuthIntent
    return_to: str


class OAuthCoordinator:
    credential_key = "google-oauth"
    scopes_key = "google-oauth-scopes"

    def __init__(self, provider: OAuthProvider, credentials: CredentialStore) -> None:
        self._provider = provider
        self._credentials = credentials
        self._pending: dict[str, PendingOAuth] = {}

    def start(
        self,
        intent: OAuthIntent = OAuthIntent.READ,
        *,
        return_to: str = "/review",
    ) -> OAuthStart:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        safe_return_to = self._safe_return_to(return_to)
        self._pending[state] = PendingOAuth(verifier, intent, safe_return_to)
        return OAuthStart(
            state=state,
            authorization_url=self._provider.authorization_url(
                state=state,
                code_challenge=challenge,
                intent=intent,
            ),
        )

    def complete(self, *, code: str, state: str) -> OAuthCompletion:
        pending = self._pending.pop(state, None)
        if pending is None:
            raise InvalidOAuthState("OAuth state is missing, expired, or does not match")
        token = self._provider.exchange_code(
            code=code,
            code_verifier=pending.verifier,
            intent=pending.intent,
        )
        self._credentials.set(self.credential_key, token.serialized_credentials)
        self._credentials.set(self.scopes_key, json.dumps(sorted(token.scopes)))
        return OAuthCompletion(token=token, return_to=pending.return_to)

    def current_scopes(self) -> tuple[str, ...]:
        encoded = self._credentials.get(self.scopes_key)
        if encoded is None:
            return ()
        try:
            scopes = json.loads(encoded)
        except json.JSONDecodeError:
            return ()
        return tuple(str(scope) for scope in scopes) if isinstance(scopes, list) else ()

    def is_connected(self) -> bool:
        return self._credentials.get(self.credential_key) is not None

    def disconnect(self) -> None:
        self._credentials.delete(self.credential_key)
        self._credentials.delete(self.scopes_key)

    @staticmethod
    def _safe_return_to(return_to: str) -> str:
        parsed = urlsplit(return_to)
        if (
            not return_to.startswith("/")
            or return_to.startswith("//")
            or "\\" in return_to
            or any(ord(character) < 32 for character in return_to)
            or parsed.scheme
            or parsed.netloc
        ):
            raise ValueError("OAuth return path must be local")
        return return_to
