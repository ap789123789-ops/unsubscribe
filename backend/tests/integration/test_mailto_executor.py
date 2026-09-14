from uuid import uuid4

from app.actions.planner import ExactMailDraft
from app.domain.state_machine import ActionState
from app.executors.mailto import MailtoExecutor, SendAuthorizationRequired
from app.executors.models import MailtoPayload


class Journal:
    def __init__(self) -> None:
        self.message_ids: list[tuple[str, str]] = []

    def persist_outbound_message_id(self, action_id: str, message_id: str) -> None:
        self.message_ids.append((action_id, message_id))


class Gmail:
    def __init__(self, *, can_send=True, send_error=None, reconciled=None) -> None:
        self.can_send = can_send
        self.send_error = send_error
        self.reconciled = reconciled
        self.send_calls = []
        self.find_calls = []

    async def has_send_scope(self) -> bool:
        return self.can_send

    async def send_mailto_unsubscribe(self, draft, message_id):
        self.send_calls.append((draft, message_id))
        if self.send_error:
            raise self.send_error
        return "gmail-sent-1"

    async def find_sent_by_message_id(self, message_id):
        self.find_calls.append(message_id)
        return self.reconciled


async def test_mailto_persists_message_id_before_single_send() -> None:
    gmail = Gmail()
    journal = Journal()
    action_id = str(uuid4())
    payload = MailtoPayload(
        draft=ExactMailDraft("leave@example.com", "Unsubscribe", "Please remove me")
    )

    result = await MailtoExecutor(gmail=gmail, journal=journal).execute(action_id, payload)

    assert result.state is ActionState.SUBMITTED
    assert result.external_id == "gmail-sent-1"
    assert len(gmail.send_calls) == 1
    assert journal.message_ids == [(action_id, gmail.send_calls[0][1])]
    assert gmail.send_calls[0][1].startswith("<unsubscribe-")


async def test_mailto_uncertainty_reconciles_without_resending() -> None:
    gmail = Gmail(send_error=TimeoutError("response lost"), reconciled="gmail-found-1")
    journal = Journal()

    result = await MailtoExecutor(gmail=gmail, journal=journal).execute(
        str(uuid4()),
        MailtoPayload(ExactMailDraft("leave@example.com", "Unsubscribe", "Remove me")),
    )

    assert result.state is ActionState.SUBMITTED
    assert result.external_id == "gmail-found-1"
    assert len(gmail.send_calls) == 1
    assert len(gmail.find_calls) == 1


async def test_mailto_absent_reconciliation_needs_user_and_never_retries() -> None:
    gmail = Gmail(send_error=TimeoutError("response lost"), reconciled=None)

    result = await MailtoExecutor(gmail=gmail, journal=Journal()).execute(
        str(uuid4()),
        MailtoPayload(ExactMailDraft("leave@example.com", "Unsubscribe", "Remove me")),
    )

    assert result.state is ActionState.NEEDS_USER
    assert len(gmail.send_calls) == 1
    assert len(gmail.find_calls) == 1


async def test_mailto_requires_send_scope_before_any_attempt() -> None:
    gmail = Gmail(can_send=False)
    journal = Journal()

    try:
        await MailtoExecutor(gmail=gmail, journal=journal).execute(
            str(uuid4()),
            MailtoPayload(ExactMailDraft("leave@example.com", "Unsubscribe", "Remove me")),
        )
    except SendAuthorizationRequired:
        pass
    else:
        raise AssertionError("missing send scope should stop execution")

    assert gmail.send_calls == []
    assert journal.message_ids == []
