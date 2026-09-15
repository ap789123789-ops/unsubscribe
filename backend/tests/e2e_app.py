import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from app.actions.browser_sessions import BrowserSessionService
from app.actions.coordinator import ExecutionCoordinator
from app.actions.planner import ActionPlanService
from app.candidates.grouper import EvaluatedMessage
from app.config import Settings
from app.domain.models import ClassificationCategory, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.email_processing.unsubscribe import DiscoveredMethod
from app.executors.browser import BrowserSessionSnapshot
from app.executors.mailto import MailtoExecutor
from app.executors.models import ExecutionResult
from app.executors.rfc8058 import HttpResponse, Rfc8058Executor
from app.gmail.oauth import OAuthCoordinator
from app.gmail.protocols import OAuthIntent, OAuthToken
from app.main import create_app
from app.persistence.database import create_database_engine, create_session_factory, run_migrations
from app.persistence.repositories import ActionRepository
from app.pipeline import InMemoryCandidateCatalog
from app.security.payload_crypto import PayloadCipher
from app.security.url_policy import UrlSafetyPolicy


def test_catalog() -> InMemoryCandidateCatalog:
    catalog = InMemoryCandidateCatalog()
    catalog.add(
        EvaluatedMessage(
            gmail_id="fixture-marketing-1",
            sender="Morning Brief <brief@example.com>",
            subject="This week in product",
            sent_at=datetime(2026, 9, 14, 12, tzinfo=UTC),
            list_id="brief.example.com",
            category=ClassificationCategory.MARKETING,
            confidence=0.93,
            methods=(
                DiscoveredMethod(
                    method=UnsubscribeMethod.RFC8058,
                    target="https://example.com/unsubscribe?token=private-fixture",
                    source="header",
                ),
            ),
            reason="Recurring editorial newsletter",
            evidence_quote="This week in product",
        )
    )
    catalog.add(
        EvaluatedMessage(
            gmail_id="fixture-unclear-1",
            sender="Community <hello@community.example>",
            subject="September update",
            sent_at=datetime(2026, 9, 12, 12, tzinfo=UTC),
            list_id="community.example",
            category=ClassificationCategory.UNCLEAR,
            confidence=0.52,
            methods=(
                DiscoveredMethod(
                    method=UnsubscribeMethod.BROWSER,
                    target="https://community.example/preferences?token=private-fixture",
                    source="header-or-body",
                ),
            ),
            reason="Mixed editorial and account content",
            evidence_quote="September update",
        )
    )
    catalog.add(
        EvaluatedMessage(
            gmail_id="fixture-accessibility-1",
            sender="Design Forum <hello@design-forum.example>",
            subject="Accessibility round-up",
            sent_at=datetime(2026, 9, 11, 12, tzinfo=UTC),
            list_id="design-forum.example",
            category=ClassificationCategory.UNCLEAR,
            confidence=0.55,
            methods=(
                DiscoveredMethod(
                    method=UnsubscribeMethod.BROWSER,
                    target="https://design-forum.example/preferences?token=private-fixture",
                    source="header-or-body",
                ),
            ),
            reason="Community content with an ambiguous account relationship",
            evidence_quote="Accessibility round-up",
        )
    )
    catalog.add(
        EvaluatedMessage(
            gmail_id="fixture-mailto-1",
            sender="Mailing Club <club@example.net>",
            subject="Club dispatch",
            sent_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
            list_id="club.example.net",
            category=ClassificationCategory.MARKETING,
            confidence=0.88,
            methods=(
                DiscoveredMethod(
                    method=UnsubscribeMethod.MAILTO,
                    target=(
                        "mailto:leave@example.net?subject=Remove%20me"
                        "&body=Please%20unsubscribe%20this%20address"
                    ),
                    source="header",
                ),
            ),
            reason="Recurring mailing list dispatch",
            evidence_quote="Club dispatch",
        )
    )
    catalog.add(
        EvaluatedMessage(
            gmail_id="fixture-hostile-1",
            sender="Hostile Fixture <hostile@example.org>",
            subject='<img src=x onerror="window.__unsubscribeXss=1">',
            sent_at=datetime(2026, 9, 8, 12, tzinfo=UTC),
            list_id="hostile.example.org",
            category=ClassificationCategory.MARKETING,
            confidence=0.81,
            methods=(
                DiscoveredMethod(
                    method=UnsubscribeMethod.RFC8058,
                    target="https://example.org/unsubscribe?token=private-fixture",
                    source="header",
                ),
            ),
            reason="Untrusted sender-controlled display text",
            evidence_quote="<script>window.__unsubscribeXss=2</script>",
        )
    )
    catalog.add(
        EvaluatedMessage(
            gmail_id="fixture-activity-rfc-1",
            sender="Dispatch Lab 1 <dispatch@dispatch-lab-1.example>",
            subject="Agent patterns weekly",
            sent_at=datetime(2026, 9, 7, 12, tzinfo=UTC),
            list_id="dispatch-lab-1.example",
            category=ClassificationCategory.MARKETING,
            confidence=0.91,
            methods=(
                DiscoveredMethod(
                    method=UnsubscribeMethod.RFC8058,
                    target="https://dispatch-lab-1.example/leave?token=private-fixture",
                    source="header",
                ),
            ),
            reason="Recurring product newsletter",
            evidence_quote="Agent patterns weekly",
        )
    )
    catalog.add(
        EvaluatedMessage(
            gmail_id="fixture-activity-mailto-1",
            sender="Member Post 1 <news@member-post-1.example>",
            subject="Member digest",
            sent_at=datetime(2026, 9, 6, 12, tzinfo=UTC),
            list_id="member-post-1.example",
            category=ClassificationCategory.MARKETING,
            confidence=0.9,
            methods=(
                DiscoveredMethod(
                    method=UnsubscribeMethod.MAILTO,
                    target=(
                        "mailto:remove@member-post-1.example?subject=Unsubscribe"
                        "&body=Please%20remove%20this%20address"
                    ),
                    source="header",
                ),
            ),
            reason="Recurring membership digest",
            evidence_quote="Member digest",
        )
    )
    catalog.add(
        EvaluatedMessage(
            gmail_id="fixture-activity-browser-1",
            sender="Product Circle 1 <hello@product-circle-1.example>",
            subject="Circle highlights",
            sent_at=datetime(2026, 9, 5, 12, tzinfo=UTC),
            list_id="product-circle-1.example",
            category=ClassificationCategory.MARKETING,
            confidence=0.86,
            methods=(
                DiscoveredMethod(
                    method=UnsubscribeMethod.BROWSER,
                    target="https://product-circle-1.example/preferences?token=private-fixture",
                    source="header-or-body",
                ),
            ),
            reason="Recurring community marketing roundup",
            evidence_quote="Circle highlights",
        )
    )
    for sample_index in range(2, 6):
        catalog.add(
            EvaluatedMessage(
                gmail_id=f"fixture-activity-rfc-{sample_index}",
                sender=(
                    f"Dispatch Lab {sample_index} <dispatch@dispatch-lab-{sample_index}.example>"
                ),
                subject="Agent patterns weekly",
                sent_at=datetime(2026, 9, 7 - sample_index, 12, tzinfo=UTC),
                list_id=f"dispatch-lab-{sample_index}.example",
                category=ClassificationCategory.MARKETING,
                confidence=0.91,
                methods=(
                    DiscoveredMethod(
                        method=UnsubscribeMethod.RFC8058,
                        target=(
                            f"https://dispatch-lab-{sample_index}.example/leave"
                            "?token=private-fixture"
                        ),
                        source="header",
                    ),
                ),
                reason="Recurring product newsletter",
                evidence_quote="Agent patterns weekly",
            )
        )
        catalog.add(
            EvaluatedMessage(
                gmail_id=f"fixture-activity-mailto-{sample_index}",
                sender=(f"Member Post {sample_index} <news@member-post-{sample_index}.example>"),
                subject="Member digest",
                sent_at=datetime(2026, 9, 7 - sample_index, 11, tzinfo=UTC),
                list_id=f"member-post-{sample_index}.example",
                category=ClassificationCategory.MARKETING,
                confidence=0.9,
                methods=(
                    DiscoveredMethod(
                        method=UnsubscribeMethod.MAILTO,
                        target=(
                            f"mailto:remove@member-post-{sample_index}.example"
                            "?subject=Unsubscribe&body=Please%20remove%20this%20address"
                        ),
                        source="header",
                    ),
                ),
                reason="Recurring membership digest",
                evidence_quote="Member digest",
            )
        )
        catalog.add(
            EvaluatedMessage(
                gmail_id=f"fixture-activity-browser-{sample_index}",
                sender=(
                    f"Product Circle {sample_index} <hello@product-circle-{sample_index}.example>"
                ),
                subject="Circle highlights",
                sent_at=datetime(2026, 9, 7 - sample_index, 10, tzinfo=UTC),
                list_id=f"product-circle-{sample_index}.example",
                category=ClassificationCategory.MARKETING,
                confidence=0.86,
                methods=(
                    DiscoveredMethod(
                        method=UnsubscribeMethod.BROWSER,
                        target=(
                            f"https://product-circle-{sample_index}.example/preferences"
                            "?token=private-fixture"
                        ),
                        source="header-or-body",
                    ),
                ),
                reason="Recurring community marketing roundup",
                evidence_quote="Circle highlights",
            )
        )
    return catalog


class StaticPublicResolver:
    async def resolve(self, hostname: str) -> tuple[str, ...]:
        return ("93.184.216.34",)


class AcceptedRfcTransport:
    async def post(self, **kwargs) -> HttpResponse:
        return HttpResponse(status_code=204, body=b"")


class AuthorizedFixtureGmail:
    async def has_send_scope(self) -> bool:
        return True

    async def send_mailto_unsubscribe(self, draft, message_id: str) -> str:
        return f"fixture-mail-{message_id}"

    async def find_sent_by_message_id(self, message_id: str) -> str | None:
        return None


class FixtureCredentials:
    def __init__(self) -> None:
        self.values = {
            "google-oauth": "fixture-credentials",
            "google-oauth-scopes": (
                '["https://www.googleapis.com/auth/gmail.readonly", '
                '"https://www.googleapis.com/auth/gmail.send"]'
            ),
        }

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


class FixtureOAuthProvider:
    def authorization_url(self, *, state: str, code_challenge: str, intent: OAuthIntent) -> str:
        return f"https://accounts.example.test/auth?state={state}&intent={intent.value}"

    def exchange_code(self, *, code: str, code_verifier: str, intent: OAuthIntent) -> OAuthToken:
        return OAuthToken(
            serialized_credentials="fixture-credentials",
            scopes=(
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
            ),
        )

    def revoke(self, serialized_credentials: str) -> bool:
        return True


class ControlledBrowserBoundary:
    def __init__(self) -> None:
        self.sessions: dict[str, BrowserSessionSnapshot] = {}

    async def execute(self, action_id: str, payload) -> ExecutionResult:
        session_id = f"browser-{action_id}"
        self.sessions[session_id] = BrowserSessionSnapshot(
            id=session_id,
            action_id=action_id,
            state=ActionState.NEEDS_USER,
            blocker_code="login_required",
            blocker_detail="Sign in to the sender's site, then resume automation.",
            origin=payload.target.origin,
            navigation_count=1,
            blocked_request_count=1,
            final_click_issued=False,
            manual_takeover=False,
        )
        return ExecutionResult(
            state=ActionState.NEEDS_USER,
            evidence_code="login_required",
            safe_detail="Sign in to the sender's site, then resume automation.",
            external_id=session_id,
        )

    def get_snapshot(self, session_id: str | None) -> BrowserSessionSnapshot:
        if session_id is None or session_id not in self.sessions:
            raise KeyError("Browser session not found")
        return self.sessions[session_id]

    async def take_over(self, session_id: str) -> BrowserSessionSnapshot:
        current = self.get_snapshot(session_id)
        updated = replace(current, manual_takeover=True)
        self.sessions[session_id] = updated
        return updated

    async def resume(self, session_id: str) -> ExecutionResult:
        self.sessions.pop(session_id)
        return ExecutionResult(
            state=ActionState.CONFIRMED,
            evidence_code="browser_semantic_acceptance_v1",
            safe_detail="The controlled page explicitly acknowledged the request.",
        )

    async def cancel(self, session_id: str) -> BrowserSessionSnapshot:
        return self.sessions.pop(session_id)


e2e_root = Path(tempfile.mkdtemp(prefix="unsubscribe-cross-stack-"))
database_url = f"sqlite:///{e2e_root / 'e2e.sqlite3'}"
run_migrations(database_url)
sessions = create_session_factory(create_database_engine(database_url))
repository = ActionRepository(sessions)
catalog = test_catalog()
policy = UrlSafetyPolicy(StaticPublicResolver())
plans = ActionPlanService(catalog, url_policy=policy)
browser_boundary = ControlledBrowserBoundary()
coordinator = ExecutionCoordinator(
    plans=plans,
    repository=repository,
    cipher=PayloadCipher(b"e" * 32),
    rfc8058=Rfc8058Executor(policy=policy, transport=AcceptedRfcTransport()),
    mailto=MailtoExecutor(gmail=AuthorizedFixtureGmail(), journal=repository),
    browser=browser_boundary,  # type: ignore[arg-type]
)
browser_sessions = BrowserSessionService(
    executor=browser_boundary,  # type: ignore[arg-type]
    registry=browser_boundary,  # type: ignore[arg-type]
    repository=repository,
)
app = create_app(
    settings=Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url=database_url,
        google_client_secrets_file=None,
        browser_profile_root=e2e_root / "browser-profiles",
    ),
    oauth_coordinator=OAuthCoordinator(FixtureOAuthProvider(), FixtureCredentials()),
    candidate_catalog=catalog,
    action_plan_service=plans,
    execution_coordinator=coordinator,
    browser_session_service=browser_sessions,
    event_repository=repository,
)
