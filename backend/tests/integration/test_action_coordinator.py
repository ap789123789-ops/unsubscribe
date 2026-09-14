from datetime import UTC, datetime

from sqlalchemy import select

from app.actions.coordinator import ExecutionCoordinator
from app.actions.planner import ActionPlanService, PlanSelection
from app.candidates.grouper import EvaluatedMessage
from app.domain.models import ClassificationCategory, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.email_processing.unsubscribe import DiscoveredMethod
from app.executors.mailto import MailtoExecutor
from app.executors.models import ExecutionResult
from app.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from app.persistence.models import ActionEventORM, UnsubscribeActionORM
from app.persistence.repositories import ActionRepository
from app.pipeline import InMemoryCandidateCatalog
from app.security.payload_crypto import PayloadCipher
from app.security.url_policy import ValidatedTarget


class AcceptingPolicy:
    async def validate_at_plan_time(self, target: str) -> ValidatedTarget:
        return ValidatedTarget(
            url=target,
            origin="https://example.com",
            hostname="example.com",
            addresses=("93.184.216.34",),
        )


class CountingRfc:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, payload):
        self.calls += 1
        return ExecutionResult(
            state=ActionState.SUBMITTED,
            evidence_code="rfc8058_request_accepted",
            safe_detail="Transport accepted; processing is not verified.",
        )


class AuthorizedGmail:
    async def has_send_scope(self) -> bool:
        return True

    async def send_mailto_unsubscribe(self, draft, message_id):
        raise AssertionError("mail executor should not run in this test")

    async def find_sent_by_message_id(self, message_id):
        return None


def candidate_catalog() -> InMemoryCandidateCatalog:
    catalog = InMemoryCandidateCatalog()
    catalog.add(
        EvaluatedMessage(
            gmail_id="m1",
            sender="Brief <brief@example.com>",
            subject="Weekly brief",
            sent_at=datetime(2026, 9, 1, tzinfo=UTC),
            list_id="brief.example.com",
            category=ClassificationCategory.MARKETING,
            confidence=0.9,
            methods=(
                DiscoveredMethod(
                    UnsubscribeMethod.RFC8058,
                    "https://example.com/u?secret=one",
                    "header",
                ),
            ),
        )
    )
    return catalog


async def test_confirm_is_durable_encrypted_and_duplicate_safe(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'actions.sqlite3'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    repository = ActionRepository(sessions)
    catalog = candidate_catalog()
    plans = ActionPlanService(catalog, url_policy=AcceptingPolicy())
    candidate = catalog.candidates()[0]
    plan = await plans.create([PlanSelection(candidate.id, candidate.revision)])
    rfc = CountingRfc()
    coordinator = ExecutionCoordinator(
        plans=plans,
        repository=repository,
        cipher=PayloadCipher(b"a" * 32),
        rfc8058=rfc,
        mailto=MailtoExecutor(gmail=AuthorizedGmail(), journal=repository),
    )

    first = await coordinator.confirm_and_execute(plan.id, plan.digest)
    second = await coordinator.confirm_and_execute(plan.id, plan.digest)

    assert first == second
    assert first[0].state is ActionState.SUBMITTED
    assert rfc.calls == 1
    with sessions() as session:
        row = session.scalar(select(UnsubscribeActionORM))
        assert row is not None
        assert b"secret=one" not in row.encrypted_payload
        assert len(session.scalars(select(ActionEventORM)).all()) == 3
