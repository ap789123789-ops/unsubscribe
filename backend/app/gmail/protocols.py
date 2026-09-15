from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class OAuthIntent(StrEnum):
    READ = "read"
    SEND = "send"


@dataclass(frozen=True)
class OAuthToken:
    serialized_credentials: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class GmailMessageRef:
    id: str
    thread_id: str


@dataclass(frozen=True)
class GmailPage:
    messages: tuple[GmailMessageRef, ...]
    next_page_token: str | None


@dataclass(frozen=True)
class GmailMessage:
    id: str
    thread_id: str
    size_estimate: int
    payload: Mapping[str, Any]
    internal_date_ms: int | None = None


class CredentialStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> None: ...


class OAuthProvider(Protocol):
    def authorization_url(self, *, state: str, code_challenge: str, intent: OAuthIntent) -> str: ...

    def exchange_code(
        self, *, code: str, code_verifier: str, intent: OAuthIntent
    ) -> OAuthToken: ...

    def revoke(self, serialized_credentials: str) -> bool: ...


class GmailGateway(Protocol):
    async def list_messages(
        self,
        *,
        query: str,
        max_results: int,
        page_token: str | None,
    ) -> GmailPage: ...

    async def get_message(self, message_id: str) -> GmailMessage: ...

    async def profile_email(self) -> str: ...
