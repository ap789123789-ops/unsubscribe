import base64
import hashlib
import secrets
from dataclasses import dataclass

from app.gmail.protocols import CredentialStore, OAuthProvider, OAuthToken


class InvalidOAuthState(ValueError):
    pass


@dataclass(frozen=True)
class OAuthStart:
    state: str
    authorization_url: str


class OAuthCoordinator:
    credential_key = "google-oauth"

    def __init__(self, provider: OAuthProvider, credentials: CredentialStore) -> None:
        self._provider = provider
        self._credentials = credentials
        self._pending_verifiers: dict[str, str] = {}

    def start(self) -> OAuthStart:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        self._pending_verifiers[state] = verifier
        return OAuthStart(
            state=state,
            authorization_url=self._provider.authorization_url(
                state=state,
                code_challenge=challenge,
            ),
        )

    def complete(self, *, code: str, state: str) -> OAuthToken:
        verifier = self._pending_verifiers.pop(state, None)
        if verifier is None:
            raise InvalidOAuthState("OAuth state is missing, expired, or does not match")
        token = self._provider.exchange_code(code=code, code_verifier=verifier)
        self._credentials.set(self.credential_key, token.serialized_credentials)
        return token

    def disconnect(self) -> None:
        self._credentials.delete(self.credential_key)

