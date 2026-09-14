from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.domain.models import ActionRecord, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.persistence.models import UnsubscribeActionORM


class ActionRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, action: ActionRecord) -> None:
        with self._session_factory.begin() as session:
            session.add(
                UnsubscribeActionORM(
                    id=str(action.id),
                    plan_id=str(action.plan_id),
                    candidate_id=str(action.candidate_id),
                    idempotency_key=action.idempotency_key,
                    method=action.method.value,
                    state=action.state.value,
                    encrypted_payload=action.encrypted_payload,
                    retry_count=action.retry_count,
                    outbound_message_id=action.outbound_message_id,
                    external_id=action.external_id,
                    created_at=action.created_at,
                    updated_at=action.updated_at,
                )
            )

    def get(self, action_id: UUID) -> ActionRecord | None:
        with self._session_factory() as session:
            row = session.get(UnsubscribeActionORM, str(action_id))
            if row is None:
                return None
            return ActionRecord(
                id=UUID(row.id),
                plan_id=UUID(row.plan_id),
                candidate_id=UUID(row.candidate_id),
                idempotency_key=row.idempotency_key,
                method=UnsubscribeMethod(row.method),
                state=ActionState(row.state),
                encrypted_payload=row.encrypted_payload,
                retry_count=row.retry_count,
                outbound_message_id=row.outbound_message_id,
                external_id=row.external_id,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
            )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
