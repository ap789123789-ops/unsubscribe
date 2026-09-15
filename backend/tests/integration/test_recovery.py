import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.models import ActionRecord, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.executors.browser import BrowserSessionRegistry
from app.gmail.fake import FakeGmailGateway
from app.gmail.protocols import GmailMessage, GmailMessageRef, GmailPage
from app.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from app.persistence.models import ActionPlanORM, SubscriptionCandidateORM
from app.persistence.repositories import ActionRepository
from app.recovery import RecoveryService
from app.scan.checkpoints import SqliteScanCheckpointStore
from app.scan.service import ScanRequest, ScanService


class ReconciliationGmail:
    def __init__(self, found: dict[str, str] | None = None) -> None:
        self.found = found or {}
        self.lookups: list[str] = []

    async def find_sent_by_message_id(self, message_id: str) -> str | None:
        self.lookups.append(message_id)
        return self.found.get(message_id)


def add_action(
    repository: ActionRepository,
    sessions,
    *,
    method: UnsubscribeMethod,
    state: ActionState,
    outbound_message_id: str | None = None,
    external_id: str | None = None,
) -> ActionRecord:
    plan_id = uuid4()
    candidate_id = uuid4()
    with sessions.begin() as session:
        session.add(
            ActionPlanORM(
                id=str(plan_id),
                digest=uuid4().hex + uuid4().hex,
                status="confirmed",
                confirmed_at=datetime.now(UTC),
            )
        )
        session.add(
            SubscriptionCandidateORM(
                id=str(candidate_id),
                revision=1,
                grouping_key=f"recovery:{candidate_id}",
                category="reviewed",
                method=method.value,
                sanitized_target="example.com",
            )
        )
    action = ActionRecord(
        id=uuid4(),
        plan_id=plan_id,
        candidate_id=candidate_id,
        idempotency_key=f"recovery:{uuid4()}",
        method=method,
        state=state,
        encrypted_payload=b"ciphertext",
        outbound_message_id=outbound_message_id,
        external_id=external_id,
    )
    repository.add(action)
    return action


async def test_recovery_reconciles_mail_and_pauses_unknown_side_effects(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'recovery.sqlite3'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    repository = ActionRepository(sessions)
    rfc = add_action(
        repository,
        sessions,
        method=UnsubscribeMethod.RFC8058,
        state=ActionState.EXECUTING,
    )
    browser = add_action(
        repository,
        sessions,
        method=UnsubscribeMethod.BROWSER,
        state=ActionState.EXECUTING,
    )
    mail = add_action(
        repository,
        sessions,
        method=UnsubscribeMethod.MAILTO,
        state=ActionState.EXECUTING,
        outbound_message_id="<deterministic@local.invalid>",
    )
    terminal = add_action(
        repository,
        sessions,
        method=UnsubscribeMethod.BROWSER,
        state=ActionState.CONFIRMED,
    )
    unstarted = add_action(
        repository,
        sessions,
        method=UnsubscribeMethod.RFC8058,
        state=ActionState.CONFIRMED_BY_USER,
    )
    paused_browser = add_action(
        repository,
        sessions,
        method=UnsubscribeMethod.BROWSER,
        state=ActionState.NEEDS_USER,
        external_id="lost-browser-session",
    )
    gmail = ReconciliationGmail({"<deterministic@local.invalid>": "gmail-sent-recovered"})

    report = await RecoveryService(repository=repository, gmail=gmail).run()

    assert repository.get(rfc.id).state is ActionState.NEEDS_USER
    assert repository.get(browser.id).state is ActionState.NEEDS_USER
    recovered_mail = repository.get(mail.id)
    assert recovered_mail.state is ActionState.SUBMITTED
    assert recovered_mail.external_id == "gmail-sent-recovered"
    assert repository.get(terminal.id).state is ActionState.CONFIRMED
    assert repository.get(unstarted.id).state is ActionState.REVIEWED
    assert repository.get(paused_browser.id).state is ActionState.REVIEWED
    assert gmail.lookups == ["<deterministic@local.invalid>"]
    assert report.reconciled_mail == 1
    assert report.paused_actions == 2
    assert report.paused_unstarted_actions == 1
    assert report.closed_browser_sessions == 1


async def test_recovery_defers_an_incomplete_scan_until_the_user_retries(
    tmp_path,
) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'scan-recovery.sqlite3'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    checkpoints = SqliteScanCheckpointStore(sessions)
    request = ScanRequest(scan_id="interrupted-scan", days=14, max_messages=25)
    checkpoints.remember_request(request)
    checkpoints.mark_seen(request.scan_id, "already-read")
    checkpoints.checkpoint_page(request.scan_id, "next-page")
    gateway = FakeGmailGateway(
        pages={
            "next-page": GmailPage((GmailMessageRef("remaining", "thread-2"),), None),
        },
        messages={
            "already-read": GmailMessage("already-read", "thread-1", 10, {}),
            "remaining": GmailMessage("remaining", "thread-2", 20, {}),
        },
    )
    received: list[str] = []
    repository = ActionRepository(sessions)
    interrupted_action = add_action(
        repository,
        sessions,
        method=UnsubscribeMethod.RFC8058,
        state=ActionState.EXECUTING,
    )

    def receive_after_side_effect_reconciliation(message: GmailMessage) -> None:
        assert repository.get(interrupted_action.id).state is ActionState.NEEDS_USER
        received.append(message.id)

    scans = ScanService(
        gateway,
        checkpoints,
        receive_after_side_effect_reconciliation,
    )

    report = await RecoveryService(
        repository=repository,
        gmail=ReconciliationGmail(),
        scan_service=scans,
        scan_checkpoints=checkpoints,
    ).run()

    assert report.deferred_scans == 1
    assert report.resumed_scans == 0
    assert report.rehydrated_messages == 0
    assert received == []
    assert checkpoints.is_complete(request.scan_id) is False
    assert gateway.read_attempts == {}


async def test_recovery_removes_only_expired_isolated_browser_profiles(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'profile-recovery.sqlite3'}")
    initialize_database(engine)
    repository = ActionRepository(create_session_factory(engine))
    profile_root = tmp_path / "profiles"
    registry = BrowserSessionRegistry(profile_root)
    expired = profile_root / "session-expired"
    fresh = profile_root / "session-fresh"
    unrelated = profile_root / "keep-me"
    for path in (expired, fresh, unrelated):
        path.mkdir()
    now = datetime(2026, 9, 14, 17, tzinfo=UTC)
    old_timestamp = (now - timedelta(hours=2)).timestamp()
    os.utime(expired, (old_timestamp, old_timestamp))
    os.utime(unrelated, (old_timestamp, old_timestamp))

    report = await RecoveryService(
        repository=repository,
        browser_registry=registry,
        clock=lambda: now,
        browser_profile_ttl=timedelta(hours=1),
    ).run()

    assert report.removed_profiles == 1
    assert expired.exists() is False
    assert fresh.is_dir()
    assert unrelated.is_dir()
