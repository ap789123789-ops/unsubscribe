from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from app.actions.planner import exact_mail_draft  # noqa: E402
from app.classification.openai_agent import OpenAIAgentsClassifier  # noqa: E402
from app.config import Settings  # noqa: E402
from app.domain.state_machine import ActionState  # noqa: E402
from app.email_processing.normalizer import EmailNormalizer  # noqa: E402
from app.executors.browser import BrowserExecutor, BrowserSessionRegistry  # noqa: E402
from app.executors.mailto import MailtoExecutor  # noqa: E402
from app.executors.models import BrowserPayload, MailtoPayload, Rfc8058Payload  # noqa: E402
from app.executors.rfc8058 import HttpxRfcTransport, Rfc8058Executor  # noqa: E402
from app.gmail.google_gateway import StoredCredentialGmailGateway  # noqa: E402
from app.security.secrets import KeyringCredentialStore  # noqa: E402
from app.security.url_policy import UrlSafetyPolicy  # noqa: E402

ACKNOWLEDGEMENT = "I_UNDERSTAND_THIS_SENDS_REAL_UNSUBSCRIBE_REQUESTS"


class SmokeGateError(RuntimeError):
    """A user-actionable smoke failure whose message contains no provider-controlled data."""


class SmokeJournal:
    def __init__(self) -> None:
        self.message_id: str | None = None

    def persist_outbound_message_id(self, action_id: str, message_id: str) -> None:
        self.message_id = message_id


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SmokeGateError(f"{name} is required for the credentialed smoke test")
    return value


async def run() -> None:
    if os.environ.get("UNSUBSCRIBE_REAL_SMOKE_ACK") != ACKNOWLEDGEMENT:
        raise SmokeGateError(
            "Set UNSUBSCRIBE_REAL_SMOKE_ACK to the documented acknowledgement before running"
        )
    settings = Settings()
    if settings.openai_api_key is None:
        raise SmokeGateError("OPENAI_API_KEY is required in the project .env file")
    expected_email = required("UNSUBSCRIBE_SMOKE_EXPECTED_GMAIL").casefold()
    rfc_url = required("UNSUBSCRIBE_SMOKE_RFC_URL")
    mailto_target = required("UNSUBSCRIBE_SMOKE_MAILTO")
    browser_url = required("UNSUBSCRIBE_SMOKE_BROWSER_URL")

    credential_store = KeyringCredentialStore()
    gmail = StoredCredentialGmailGateway(credential_store)
    try:
        actual_email = (await gmail.profile_email()).casefold()
    except Exception as error:
        raise SmokeGateError(
            "Gmail profile verification failed; provider details were suppressed"
        ) from error
    if actual_email != expected_email:
        raise SmokeGateError("The connected Gmail account does not match the expected account")
    print("1/4 The expected Gmail OAuth credential and profile were verified.")

    query = os.environ.get("UNSUBSCRIBE_SMOKE_GMAIL_QUERY", "newer_than:30d")
    try:
        page = await gmail.list_messages(query=query, max_results=1, page_token=None)
    except Exception as error:
        raise SmokeGateError(
            "Gmail message listing failed; provider details were suppressed"
        ) from error
    if not page.messages:
        raise SmokeGateError("The smoke Gmail query returned no message")
    try:
        message = await gmail.get_message(page.messages[0].id)
    except Exception as error:
        raise SmokeGateError(
            "Gmail message retrieval failed; provider details were suppressed"
        ) from error
    normalized = EmailNormalizer().normalize(message)
    if normalized.oversized or not normalized.model_text.strip():
        raise SmokeGateError("The selected Gmail message did not yield a readable complete body")
    try:
        model_result = await OpenAIAgentsClassifier(
            model="gpt-5-mini",
            api_key=settings.openai_api_key.get_secret_value(),
        ).classify(normalized)
    except Exception as error:
        raise SmokeGateError(
            "OpenAI classification failed; provider details were suppressed"
        ) from error
    if model_result.category.value not in {"marketing", "non_marketing", "unclear"}:
        raise SmokeGateError("The model returned an invalid category")
    print("2/4 A complete Gmail body was classified by gpt-5-mini.")

    policy = UrlSafetyPolicy()
    try:
        rfc_target = await policy.validate_at_plan_time(rfc_url)
        rfc_result = await Rfc8058Executor(
            policy=policy,
            transport=HttpxRfcTransport(),
        ).execute(Rfc8058Payload(rfc_target))
    except Exception as error:
        raise SmokeGateError(
            "Controlled RFC smoke failed; target details were suppressed"
        ) from error
    if rfc_result.state is not ActionState.SUBMITTED:
        raise SmokeGateError(f"Controlled RFC smoke ended in {rfc_result.state.value}")

    try:
        mail_result = await MailtoExecutor(gmail=gmail, journal=SmokeJournal()).execute(
            str(uuid4()),
            MailtoPayload(exact_mail_draft(mailto_target)),
        )
    except Exception as error:
        raise SmokeGateError(
            "Controlled mailto smoke failed; target details were suppressed"
        ) from error
    if mail_result.state is not ActionState.SUBMITTED:
        raise SmokeGateError(f"Controlled mailto smoke ended in {mail_result.state.value}")
    print("3/4 Controlled RFC 8058 and mailto requests were submitted once.")

    browser: BrowserExecutor | None = None
    try:
        browser_target = await policy.validate_at_plan_time(browser_url)
        registry = BrowserSessionRegistry()
        browser = BrowserExecutor(policy=policy, registry=registry, headless=False)
        browser_result = await browser.execute(
            str(uuid4()),
            BrowserPayload(browser_target),
        )
        if browser_result.state not in {ActionState.CONFIRMED, ActionState.SUBMITTED}:
            raise SmokeGateError(f"Controlled browser smoke ended in {browser_result.state.value}")
    except SmokeGateError:
        raise
    except Exception as error:
        raise SmokeGateError(
            "Controlled browser smoke failed; target details were suppressed"
        ) from error
    finally:
        if browser is not None:
            await browser.close_all()
    print("4/4 Controlled visible-browser request reached an honest accepted state.")


def main() -> None:
    try:
        asyncio.run(run())
    except SmokeGateError as error:
        raise SystemExit(f"Credentialed smoke failed: {error}") from None
    except Exception:  # noqa: BLE001 - never echo provider-controlled exception text
        raise SystemExit(
            "Credentialed smoke failed unexpectedly; sensitive provider details were suppressed"
        ) from None


if __name__ == "__main__":
    main()
