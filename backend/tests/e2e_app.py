from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from app.actions.planner import ActionPlanService
from app.candidates.grouper import EvaluatedMessage
from app.domain.models import ActionRecord, ClassificationCategory, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.email_processing.unsubscribe import DiscoveredMethod
from app.executors.browser import BrowserSessionSnapshot
from app.main import create_app
from app.pipeline import InMemoryCandidateCatalog


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
    return catalog


class TestCoordinator:
    def __init__(self, plans: ActionPlanService) -> None:
        self.plans = plans
        self.actions: dict[str, tuple[ActionRecord, ...]] = {}

    async def confirm_and_execute(self, plan_id: str, digest: str) -> tuple[ActionRecord, ...]:
        plan, is_new = await self.plans.confirm(plan_id, digest)
        if not is_new:
            return self.actions[plan_id]
        actions = tuple(
            ActionRecord(
                id=uuid5(NAMESPACE_URL, f"e2e:{plan.id}:{item.candidate_id}"),
                plan_id=UUID(plan.id),
                candidate_id=UUID(item.candidate_id),
                idempotency_key=f"e2e:{plan.id}:{item.candidate_id}",
                method=item.method,
                state=(
                    ActionState.NEEDS_USER
                    if item.method is UnsubscribeMethod.BROWSER
                    else ActionState.SUBMITTED
                ),
                encrypted_payload=b"e2e-ciphertext",
                external_id=(
                    f"browser-{plan.id}"
                    if item.method is UnsubscribeMethod.BROWSER
                    else "external-fixture"
                ),
            )
            for item in plan.items
        )
        self.actions[plan_id] = actions
        return actions

    def actions_for_plan(self, plan_id: str) -> tuple[ActionRecord, ...]:
        return self.actions.get(plan_id, ())

    def update_browser(self, session_id: str, state: ActionState) -> ActionRecord:
        for plan_id, actions in self.actions.items():
            for index, action in enumerate(actions):
                if (
                    action.method is UnsubscribeMethod.BROWSER
                    and action.external_id == session_id
                ):
                    updated = action.model_copy(
                        update={
                            "state": state,
                            "external_id": (
                            None
                            if state is not ActionState.NEEDS_USER
                            else action.external_id
                            ),
                        }
                    )
                    self.actions[plan_id] = actions[:index] + (updated,) + actions[index + 1 :]
                    return updated
        raise KeyError("Browser action not found")

    def browser_action(self, session_id: str) -> ActionRecord:
        for actions in self.actions.values():
            for action in actions:
                if (
                    action.method is UnsubscribeMethod.BROWSER
                    and action.external_id == session_id
                ):
                    return action
        raise KeyError("Browser action not found")


class TestBrowserSessions:
    def __init__(self, coordinator: TestCoordinator) -> None:
        self.coordinator = coordinator
        self.manual_takeovers: set[str] = set()

    def get(self, session_id: str) -> BrowserSessionSnapshot:
        action = self.coordinator.browser_action(session_id)
        return BrowserSessionSnapshot(
            id=session_id,
            action_id=str(action.id),
            state=action.state,
            blocker_code="login_required",
            blocker_detail="Sign in to the sender's site, then resume automation.",
            origin="https://community.example",
            navigation_count=1,
            blocked_request_count=1,
            final_click_issued=False,
            manual_takeover=session_id in self.manual_takeovers,
        )

    async def take_over(self, session_id: str) -> BrowserSessionSnapshot:
        self.manual_takeovers.add(session_id)
        return self.get(session_id)

    async def resume(self, session_id: str) -> ActionRecord:
        return self.coordinator.update_browser(session_id, ActionState.CONFIRMED)

    async def cancel(self, session_id: str) -> ActionRecord:
        return self.coordinator.update_browser(session_id, ActionState.REVIEWED)


catalog = test_catalog()
plans = ActionPlanService(catalog)
coordinator = TestCoordinator(plans)
app = create_app(
    candidate_catalog=catalog,
    action_plan_service=plans,
    execution_coordinator=coordinator,  # type: ignore[arg-type]
    browser_session_service=TestBrowserSessions(coordinator),  # type: ignore[arg-type]
)
