from dataclasses import dataclass

from app.actions.planner import ExactMailDraft
from app.domain.state_machine import ActionState
from app.security.url_policy import ValidatedTarget


@dataclass(frozen=True)
class Rfc8058Payload:
    target: ValidatedTarget


@dataclass(frozen=True)
class MailtoPayload:
    draft: ExactMailDraft


@dataclass(frozen=True)
class BrowserPayload:
    target: ValidatedTarget


@dataclass(frozen=True)
class ExecutionResult:
    state: ActionState
    evidence_code: str
    safe_detail: str
    retryable: bool = False
    external_id: str | None = None
