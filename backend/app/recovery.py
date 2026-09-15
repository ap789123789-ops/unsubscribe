from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.domain.models import UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.executors.browser import BrowserSessionRegistry
from app.persistence.repositories import ActionRepository
from app.scan.service import ScanCheckpointStore, ScanService


class SentMailReconciler(Protocol):
    async def find_sent_by_message_id(self, message_id: str) -> str | None: ...


class StartupRecovery(Protocol):
    async def run(self) -> object: ...


@dataclass(frozen=True)
class RecoveryReport:
    reconciled_mail: int = 0
    paused_actions: int = 0
    paused_unstarted_actions: int = 0
    resumed_scans: int = 0
    rehydrated_messages: int = 0
    rehydration_failures: int = 0
    failed_scans: int = 0
    removed_profiles: int = 0
    closed_browser_sessions: int = 0


class RecoveryService:
    def __init__(
        self,
        *,
        repository: ActionRepository,
        gmail: SentMailReconciler | None = None,
        scan_service: ScanService | None = None,
        scan_checkpoints: ScanCheckpointStore | None = None,
        browser_registry: BrowserSessionRegistry | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        browser_profile_ttl: timedelta = timedelta(hours=1),
    ) -> None:
        self._repository = repository
        self._gmail = gmail
        self._scan_service = scan_service
        self._scan_checkpoints = scan_checkpoints
        self._browser_registry = browser_registry
        self._clock = clock
        self._browser_profile_ttl = browser_profile_ttl

    async def run(self) -> RecoveryReport:
        reconciled_mail = 0
        paused_actions = 0
        paused_unstarted_actions = 0
        resumed_scans = 0
        rehydrated_messages = 0
        rehydration_failures = 0
        failed_scans = 0
        removed_profiles = 0
        active_browser_sessions = {
            snapshot.id
            for snapshot in (
                self._browser_registry.snapshots() if self._browser_registry is not None else ()
            )
        }
        if self._browser_registry is not None:
            removed_profiles = self._browser_registry.cleanup_expired(
                self._clock() - self._browser_profile_ttl
            )
        for action in self._repository.list_by_state(ActionState.EXECUTING):
            if (
                action.method is UnsubscribeMethod.MAILTO
                and action.outbound_message_id
                and self._gmail is not None
            ):
                try:
                    external_id = await self._gmail.find_sent_by_message_id(
                        action.outbound_message_id
                    )
                except Exception:  # noqa: BLE001 - startup recovery must fail safe
                    external_id = None
                if external_id is not None:
                    self._repository.set_state(
                        action.id,
                        ActionState.SUBMITTED,
                        evidence_code="mail_reconciled_after_restart",
                        safe_detail="The unsubscribe email was found in Gmail Sent after restart.",
                        external_id=external_id,
                    )
                    reconciled_mail += 1
                    continue
            self._repository.set_state(
                action.id,
                ActionState.NEEDS_USER,
                evidence_code="interrupted_action_requires_review",
                safe_detail=(
                    "The app restarted while this action was in progress; it was not repeated."
                ),
            )
            paused_actions += 1
        for action in self._repository.list_by_state(ActionState.CONFIRMED_BY_USER):
            self._repository.set_state(
                action.id,
                ActionState.REVIEWED,
                evidence_code="confirmed_action_interrupted_before_start",
                safe_detail=(
                    "The app restarted before this confirmed action began; it was not executed."
                ),
            )
            paused_unstarted_actions += 1
        closed_browser_sessions = 0
        for action in self._repository.list_by_state(ActionState.NEEDS_USER):
            if (
                action.method is UnsubscribeMethod.BROWSER
                and action.external_id
                and action.external_id not in active_browser_sessions
            ):
                self._repository.set_state(
                    action.id,
                    ActionState.REVIEWED,
                    evidence_code="browser_session_lost_after_restart",
                    safe_detail=(
                        "The prior guarded browser no longer exists; no click was repeated."
                    ),
                )
                closed_browser_sessions += 1
        if self._scan_service is not None and self._scan_checkpoints is not None:
            for request in self._scan_checkpoints.incomplete_requests():
                try:
                    rehydration = await self._scan_service.rehydrate(request)
                    rehydrated_messages += rehydration.rehydrated
                    rehydration_failures += rehydration.failed
                    await self._scan_service.run(request)
                except Exception:  # noqa: BLE001 - checkpoint remains durable for a later retry
                    failed_scans += 1
                    continue
                resumed_scans += 1
        return RecoveryReport(
            reconciled_mail=reconciled_mail,
            paused_actions=paused_actions,
            paused_unstarted_actions=paused_unstarted_actions,
            resumed_scans=resumed_scans,
            rehydrated_messages=rehydrated_messages,
            rehydration_failures=rehydration_failures,
            failed_scans=failed_scans,
            removed_profiles=removed_profiles,
            closed_browser_sessions=closed_browser_sessions,
        )
