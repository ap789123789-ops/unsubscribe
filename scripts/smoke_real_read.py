from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from app.classification.openai_agent import OpenAIAgentsClassifier  # noqa: E402
from app.config import Settings  # noqa: E402
from app.email_processing.normalizer import EmailNormalizer  # noqa: E402
from app.gmail.google_gateway import StoredCredentialGmailGateway  # noqa: E402
from app.security.secrets import KeyringCredentialStore  # noqa: E402


class SmokeGateError(RuntimeError):
    """A user-actionable failure whose message contains no provider-controlled data."""


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SmokeGateError(f"{name} is required for the real read/classification smoke test")
    return value


async def run() -> None:
    expected_email = required("UNSUBSCRIBE_SMOKE_EXPECTED_GMAIL").casefold()
    settings = Settings()
    if settings.openai_api_key is None:
        raise SmokeGateError("OPENAI_API_KEY is required in the project .env file")

    gmail = StoredCredentialGmailGateway(KeyringCredentialStore())
    try:
        actual_email = (await gmail.profile_email()).casefold()
    except Exception as error:
        raise SmokeGateError(
            "Gmail profile verification failed; connect Gmail through the local app first"
        ) from error
    if actual_email != expected_email:
        raise SmokeGateError("The connected Gmail account does not match the expected account")
    print("1/3 The expected Gmail account is connected.")

    query = os.environ.get("UNSUBSCRIBE_SMOKE_GMAIL_QUERY", "newer_than:30d").strip()
    if not query:
        raise SmokeGateError("UNSUBSCRIBE_SMOKE_GMAIL_QUERY must not be empty")
    try:
        page = await gmail.list_messages(query=query, max_results=1, page_token=None)
        if not page.messages:
            raise SmokeGateError("The Gmail smoke query returned no message")
        message = await gmail.get_message(page.messages[0].id)
    except SmokeGateError:
        raise
    except Exception as error:
        raise SmokeGateError(
            "Gmail full-message retrieval failed; provider details were suppressed"
        ) from error

    normalized = EmailNormalizer().normalize(message)
    if normalized.oversized or not normalized.text.strip():
        raise SmokeGateError("The selected message did not yield a readable complete body")
    print(f"2/3 A complete Gmail message body was read ({len(normalized.text)} text characters).")

    try:
        result = await OpenAIAgentsClassifier(
            model="gpt-5-mini",
            api_key=settings.openai_api_key.get_secret_value(),
        ).classify(normalized)
    except Exception as error:
        raise SmokeGateError(
            "OpenAI classification failed; provider details were suppressed"
        ) from error
    print(
        "3/3 gpt-5-mini returned a valid structured classification: "
        f"{result.category.value} (confidence {result.confidence:.2f})."
    )


def main() -> None:
    try:
        asyncio.run(run())
    except SmokeGateError as error:
        raise SystemExit(f"Real read/classification smoke failed: {error}") from None
    except Exception:  # noqa: BLE001 - never echo provider-controlled exception text
        raise SystemExit(
            "Real read/classification smoke failed unexpectedly; sensitive details were suppressed"
        ) from None


if __name__ == "__main__":
    main()
