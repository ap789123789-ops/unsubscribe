import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.gmail.oauth import OAuthCoordinator
from app.gmail.protocols import (
    CredentialStore,
    GmailMessage,
    GmailMessageRef,
    GmailPage,
    OAuthToken,
)

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GoogleOAuthProvider:
    def __init__(self, *, client_secrets_file: Path, redirect_uri: str) -> None:
        self._client_secrets_file = client_secrets_file
        self._redirect_uri = redirect_uri

    def _flow(self, *, code_verifier: str | None = None) -> Flow:
        return Flow.from_client_secrets_file(
            str(self._client_secrets_file),
            scopes=[GMAIL_READONLY_SCOPE],
            redirect_uri=self._redirect_uri,
            code_verifier=code_verifier,
            autogenerate_code_verifier=False,
        )

    def authorization_url(self, *, state: str, code_challenge: str) -> str:
        flow = self._flow()
        url, _ = flow.authorization_url(
            state=state,
            access_type="offline",
            prompt="consent",
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )
        return url

    def exchange_code(self, *, code: str, code_verifier: str) -> OAuthToken:
        flow = self._flow(code_verifier=code_verifier)
        flow.fetch_token(code=code)
        credentials = flow.credentials
        return OAuthToken(
            serialized_credentials=credentials.to_json(),
            scopes=tuple(credentials.scopes or (GMAIL_READONLY_SCOPE,)),
        )


class GoogleGmailGateway:
    def __init__(
        self,
        serialized_credentials: str,
        *,
        service_factory: Callable[[Credentials], Any] | None = None,
    ) -> None:
        credential_info = json.loads(serialized_credentials)
        self._credentials = Credentials.from_authorized_user_info(credential_info)
        self._service_factory = service_factory or (
            lambda credentials: build(
                "gmail",
                "v1",
                credentials=credentials,
                cache_discovery=False,
            )
        )
        self._service: Any | None = None

    def _client(self) -> Any:
        if self._service is None:
            self._service = self._service_factory(self._credentials)
        return self._service

    async def list_messages(
        self,
        *,
        query: str,
        max_results: int,
        page_token: str | None,
    ) -> GmailPage:
        def request() -> dict[str, Any]:
            kwargs: dict[str, Any] = {
                "userId": "me",
                "q": query,
                "maxResults": min(max_results, 500),
                "includeSpamTrash": False,
            }
            if page_token is not None:
                kwargs["pageToken"] = page_token
            return self._client().users().messages().list(**kwargs).execute()

        response = await asyncio.to_thread(request)
        references = tuple(
            GmailMessageRef(id=item["id"], thread_id=item["threadId"])
            for item in response.get("messages", [])
        )
        return GmailPage(
            messages=references,
            next_page_token=response.get("nextPageToken"),
        )

    async def get_message(self, message_id: str) -> GmailMessage:
        def request() -> dict[str, Any]:
            return (
                self._client()
                .users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

        response = await asyncio.to_thread(request)
        internal_date = response.get("internalDate")
        return GmailMessage(
            id=response["id"],
            thread_id=response["threadId"],
            size_estimate=int(response.get("sizeEstimate", 0)),
            payload=response.get("payload", {}),
            internal_date_ms=int(internal_date) if internal_date is not None else None,
        )

    async def profile_email(self) -> str:
        response = await asyncio.to_thread(
            lambda: self._client().users().getProfile(userId="me").execute()
        )
        return str(response["emailAddress"])


class StoredCredentialGmailGateway:
    def __init__(self, credential_store: CredentialStore) -> None:
        self._credential_store = credential_store
        self._gateway: GoogleGmailGateway | None = None

    def _connected(self) -> GoogleGmailGateway:
        if self._gateway is None:
            serialized = self._credential_store.get(OAuthCoordinator.credential_key)
            if serialized is None:
                raise RuntimeError("Gmail is not connected")
            self._gateway = GoogleGmailGateway(serialized)
        return self._gateway

    async def list_messages(
        self,
        *,
        query: str,
        max_results: int,
        page_token: str | None,
    ) -> GmailPage:
        return await self._connected().list_messages(
            query=query,
            max_results=max_results,
            page_token=page_token,
        )

    async def get_message(self, message_id: str) -> GmailMessage:
        return await self._connected().get_message(message_id)

    async def profile_email(self) -> str:
        return await self._connected().profile_email()
