from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.actions.coordinator import (
    ActionAlreadyAttempted,
    ActionRetryNotAllowed,
    ExecutionCoordinator,
)
from app.actions.planner import ActionPlan, ActionPlanService, PlannedAction, PlanSelection
from app.candidates.grouper import EvaluatedMessage
from app.domain.models import ActionRecord, ClassificationCategory, UnsubscribeMethod
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


class RecordingGmail:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def has_send_scope(self) -> bool:
        return True

    async def send_mailto_unsubscribe(self, draft, message_id):
        self.sent.append((draft.recipient, message_id))
        return "fixture-gmail-id"

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


def persist_action(repository: ActionRepository, action: ActionRecord) -> None:
    plan = ActionPlan(
        id=str(action.plan_id),
        digest=action.idempotency_key.ljust(64, "0")[:64],
        items=(
            PlannedAction(
                candidate_id=str(action.candidate_id),
                revision=1,
                sender=action.display_sender,
                subject=action.display_subject,
                method=action.method,
                target_display=action.target_display,
                target="fixture-target",
            ),
        ),
        confirmed=True,
    )
    repository.create_confirmed_plan(plan, (action,))


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


async def test_fresh_equivalent_plan_cannot_repeat_an_existing_action(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'semantic-idempotency.sqlite3'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    repository = ActionRepository(sessions)
    catalog = candidate_catalog()
    plans = ActionPlanService(catalog, url_policy=AcceptingPolicy())
    candidate = catalog.candidates()[0]
    first_plan = await plans.create([PlanSelection(candidate.id, candidate.revision)])
    second_plan = await plans.create([PlanSelection(candidate.id, candidate.revision)])
    rfc = CountingRfc()
    coordinator = ExecutionCoordinator(
        plans=plans,
        repository=repository,
        cipher=PayloadCipher(b"a" * 32),
        rfc8058=rfc,
        mailto=MailtoExecutor(gmail=AuthorizedGmail(), journal=repository),
    )

    await coordinator.confirm_and_execute(first_plan.id, first_plan.digest)
    with pytest.raises(ActionAlreadyAttempted):
        await coordinator.confirm_and_execute(second_plan.id, second_plan.digest)

    assert rfc.calls == 1


async def test_reviewed_rfc_retry_is_allowed_once_only_after_explicit_503(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'rfc-retry.sqlite3'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    repository = ActionRepository(sessions)
    cipher = PayloadCipher(b"r" * 32)
    action_id = uuid4()
    action = ActionRecord(
        id=action_id,
        plan_id=uuid4(),
        candidate_id=uuid4(),
        idempotency_key="retry-rfc-503",
        method=UnsubscribeMethod.RFC8058,
        state=ActionState.EXECUTING,
        encrypted_payload=cipher.encrypt(
            action_id,
            {"version": 1, "method": "rfc8058", "target": "https://example.com/retry"},
        ),
    )
    persist_action(repository, action)
    repository.set_state(
        action.id,
        ActionState.FAILED,
        evidence_code="http_503",
        safe_detail="The server rejected the request. A reviewed retry may be available.",
    )
    rfc = CountingRfc()
    coordinator = ExecutionCoordinator(
        plans=ActionPlanService(InMemoryCandidateCatalog()),
        repository=repository,
        cipher=cipher,
        rfc8058=rfc,
        mailto=MailtoExecutor(gmail=AuthorizedGmail(), journal=repository),
        url_policy=AcceptingPolicy(),
    )

    retried = await coordinator.review_and_retry(str(action.id))

    assert retried.state is ActionState.SUBMITTED
    assert retried.retry_count == 1
    assert rfc.calls == 1
    with pytest.raises(ActionRetryNotAllowed):
        await coordinator.review_and_retry(str(action.id))
    assert rfc.calls == 1


async def test_reviewed_retry_records_failed_when_encrypted_payload_is_unavailable(
    tmp_path,
) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'rfc-corrupt-retry.sqlite3'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    repository = ActionRepository(sessions)
    action_id = uuid4()
    action = ActionRecord(
        id=action_id,
        plan_id=uuid4(),
        candidate_id=uuid4(),
        idempotency_key="retry-rfc-corrupt-payload",
        method=UnsubscribeMethod.RFC8058,
        state=ActionState.EXECUTING,
        encrypted_payload=PayloadCipher(b"x" * 32).encrypt(
            action_id,
            {"version": 1, "method": "rfc8058", "target": "https://example.com/retry"},
        ),
    )
    persist_action(repository, action)
    repository.set_state(
        action.id,
        ActionState.FAILED,
        evidence_code="http_503",
        safe_detail="The server rejected the request. A reviewed retry may be available.",
    )
    rfc = CountingRfc()
    coordinator = ExecutionCoordinator(
        plans=ActionPlanService(InMemoryCandidateCatalog()),
        repository=repository,
        cipher=PayloadCipher(b"r" * 32),
        rfc8058=rfc,
        mailto=MailtoExecutor(gmail=AuthorizedGmail(), journal=repository),
        url_policy=AcceptingPolicy(),
    )

    result = await coordinator.review_and_retry(str(action.id))
    activity = repository.get_activity(action.id)

    assert result.state is ActionState.FAILED
    assert result.retry_count == 1
    assert activity is not None
    assert activity.evidence_code == "stored_payload_unavailable"
    assert rfc.calls == 0


async def test_mailto_can_retry_only_when_missing_authorization_proves_no_send(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'mailto-retry.sqlite3'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    repository = ActionRepository(sessions)
    cipher = PayloadCipher(b"m" * 32)
    action_id = uuid4()
    action = ActionRecord(
        id=action_id,
        plan_id=uuid4(),
        candidate_id=uuid4(),
        idempotency_key="retry-mailto-auth",
        method=UnsubscribeMethod.MAILTO,
        state=ActionState.EXECUTING,
        encrypted_payload=cipher.encrypt(
            action_id,
            {
                "version": 1,
                "method": "mailto",
                "recipient": "leave@example.net",
                "subject": "Remove me",
                "body": "Please unsubscribe this address",
            },
        ),
    )
    persist_action(repository, action)
    repository.set_state(
        action.id,
        ActionState.NEEDS_USER,
        evidence_code="gmail_send_authorization_required",
        safe_detail="Gmail send permission is no longer available.",
    )
    gmail = RecordingGmail()
    coordinator = ExecutionCoordinator(
        plans=ActionPlanService(InMemoryCandidateCatalog()),
        repository=repository,
        cipher=cipher,
        rfc8058=CountingRfc(),
        mailto=MailtoExecutor(gmail=gmail, journal=repository),
        url_policy=AcceptingPolicy(),
    )

    retried = await coordinator.review_and_retry(str(action.id))

    assert retried.state is ActionState.SUBMITTED
    assert retried.retry_count == 1
    assert [recipient for recipient, _ in gmail.sent] == ["leave@example.net"]


async def test_uncertain_submission_never_exposes_retry(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'uncertain-retry.sqlite3'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    repository = ActionRepository(sessions)
    cipher = PayloadCipher(b"u" * 32)
    action_id = uuid4()
    action = ActionRecord(
        id=action_id,
        plan_id=uuid4(),
        candidate_id=uuid4(),
        idempotency_key="retry-uncertain",
        method=UnsubscribeMethod.RFC8058,
        state=ActionState.EXECUTING,
        encrypted_payload=cipher.encrypt(
            action_id,
            {"version": 1, "method": "rfc8058", "target": "https://example.com/uncertain"},
        ),
    )
    persist_action(repository, action)
    repository.set_state(
        action.id,
        ActionState.NEEDS_USER,
        evidence_code="submission_uncertain",
        safe_detail="The request outcome is uncertain; it was not repeated.",
    )
    rfc = CountingRfc()
    coordinator = ExecutionCoordinator(
        plans=ActionPlanService(InMemoryCandidateCatalog()),
        repository=repository,
        cipher=cipher,
        rfc8058=rfc,
        mailto=MailtoExecutor(gmail=AuthorizedGmail(), journal=repository),
        url_policy=AcceptingPolicy(),
    )

    with pytest.raises(ActionRetryNotAllowed):
        await coordinator.review_and_retry(str(action.id))

    assert rfc.calls == 0
