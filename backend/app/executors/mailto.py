from hashlib import sha256
from typing import Protocol

from app.actions.planner import ExactMailDraft
from app.domain.state_machine import ActionState
from app.executors.models import ExecutionResult, MailtoPayload


class SendAuthorizationRequired(RuntimeError):
    pass


class MailtoGmailGateway(Protocol):
    async def has_send_scope(self) -> bool: ...

    async def send_mailto_unsubscribe(
        self, draft: ExactMailDraft, message_id: str
    ) -> str: ...

    async def find_sent_by_message_id(self, message_id: str) -> str | None: ...


class MailtoJournal(Protocol):
    def persist_outbound_message_id(self, action_id: str, message_id: str) -> None: ...


def deterministic_message_id(action_id: str) -> str:
    opaque = sha256(f"gmail-unsubscribe:{action_id}".encode()).hexdigest()
    return f"<unsubscribe-{opaque}@local.invalid>"


class MailtoExecutor:
    def __init__(self, *, gmail: MailtoGmailGateway, journal: MailtoJournal) -> None:
        self._gmail = gmail
        self._journal = journal

    async def is_authorized(self) -> bool:
        return await self._gmail.has_send_scope()

    async def execute(self, action_id: str, payload: MailtoPayload) -> ExecutionResult:
        if not await self.is_authorized():
            raise SendAuthorizationRequired(
                "Gmail send permission is required before sending an unsubscribe message"
            )
        message_id = deterministic_message_id(action_id)
        self._journal.persist_outbound_message_id(action_id, message_id)
        try:
            external_id = await self._gmail.send_mailto_unsubscribe(payload.draft, message_id)
        except Exception:
            external_id = await self._gmail.find_sent_by_message_id(message_id)
            if external_id is None:
                return ExecutionResult(
                    state=ActionState.NEEDS_USER,
                    evidence_code="mail_send_uncertain",
                    safe_detail="Gmail did not confirm the send; the message was not repeated.",
                )
            return ExecutionResult(
                state=ActionState.SUBMITTED,
                evidence_code="mail_reconciled_in_sent",
                safe_detail="The unsubscribe email was found in Gmail Sent.",
                external_id=external_id,
            )
        return ExecutionResult(
            state=ActionState.SUBMITTED,
            evidence_code="gmail_send_accepted",
            safe_detail="Gmail accepted the unsubscribe email; list processing is not verified.",
            external_id=external_id,
        )
