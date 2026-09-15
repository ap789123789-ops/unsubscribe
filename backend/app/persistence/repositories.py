from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.actions.planner import ActionPlan
from app.domain.models import ActionRecord, UnsubscribeMethod
from app.domain.state_machine import ActionState, transition_action
from app.persistence.models import (
    ActionEventORM,
    ActionPlanORM,
    SubscriptionCandidateORM,
    UnsubscribeActionORM,
)


@dataclass(frozen=True)
class ActionEventRecord:
    id: str
    action_id: str
    state: ActionState
    evidence_code: str | None
    safe_detail: str | None
    created_at: datetime


@dataclass(frozen=True)
class ActivityRecord:
    action: ActionRecord
    evidence_code: str | None
    safe_detail: str | None


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
                    display_sender=action.display_sender,
                    display_subject=action.display_subject,
                    target_display=action.target_display,
                    retry_count=action.retry_count,
                    outbound_message_id=action.outbound_message_id,
                    external_id=action.external_id,
                    created_at=action.created_at,
                    updated_at=action.updated_at,
                )
            )

    def create_confirmed_plan(
        self,
        plan: ActionPlan,
        actions: tuple[ActionRecord, ...],
    ) -> tuple[ActionRecord, ...]:
        with self._session_factory.begin() as session:
            existing = session.get(ActionPlanORM, plan.id)
            if existing is not None:
                return self._list_for_plan(session, plan.id)
            session.add(
                ActionPlanORM(
                    id=plan.id,
                    digest=plan.digest,
                    status="confirmed",
                    confirmed_at=datetime.now(UTC),
                )
            )
            for item in plan.items:
                if session.get(SubscriptionCandidateORM, item.candidate_id) is None:
                    session.add(
                        SubscriptionCandidateORM(
                            id=item.candidate_id,
                            revision=item.revision,
                            grouping_key=f"execution:{item.candidate_id}",
                            category="reviewed",
                            method=item.method.value,
                            sanitized_target=item.target_display,
                        )
                    )
            session.flush()
            for action in actions:
                session.add(self._to_row(action))
                session.flush()
                session.add(
                    ActionEventORM(
                        action_id=str(action.id),
                        sequence=1,
                        from_state=ActionState.SELECTED.value,
                        to_state=ActionState.CONFIRMED_BY_USER.value,
                        evidence_code="user_confirmed_plan",
                        safe_detail="The user confirmed the reviewed plan digest.",
                    )
                )
        return actions

    def list_for_plan(self, plan_id: UUID | str) -> tuple[ActionRecord, ...]:
        with self._session_factory() as session:
            return self._list_for_plan(session, str(plan_id))

    def list_by_state(self, state: ActionState) -> tuple[ActionRecord, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(UnsubscribeActionORM)
                .where(UnsubscribeActionORM.state == state.value)
                .order_by(UnsubscribeActionORM.created_at, UnsubscribeActionORM.id)
            )
            return tuple(self._from_row(row) for row in rows)

    def list_activity(
        self,
        *,
        plan_id: str | None = None,
        limit: int = 500,
    ) -> tuple[ActivityRecord, ...]:
        with self._session_factory() as session:
            statement = select(UnsubscribeActionORM)
            if plan_id is not None:
                statement = statement.where(UnsubscribeActionORM.plan_id == plan_id)
            rows = session.scalars(
                statement.order_by(
                    UnsubscribeActionORM.updated_at.desc(),
                    UnsubscribeActionORM.id.desc(),
                ).limit(limit)
            )
            activity: list[ActivityRecord] = []
            for row in rows:
                latest_event = session.scalar(
                    select(ActionEventORM)
                    .where(ActionEventORM.action_id == row.id)
                    .order_by(ActionEventORM.stream_sequence.desc())
                    .limit(1)
                )
                activity.append(
                    ActivityRecord(
                        action=self._from_row(row),
                        evidence_code=(latest_event.evidence_code if latest_event else None),
                        safe_detail=(latest_event.safe_detail if latest_event else None),
                    )
                )
            return tuple(activity)

    def get_activity(self, action_id: UUID | str) -> ActivityRecord | None:
        with self._session_factory() as session:
            row = session.get(UnsubscribeActionORM, str(action_id))
            if row is None:
                return None
            latest_event = session.scalar(
                select(ActionEventORM)
                .where(ActionEventORM.action_id == row.id)
                .order_by(ActionEventORM.stream_sequence.desc())
                .limit(1)
            )
            return ActivityRecord(
                action=self._from_row(row),
                evidence_code=(latest_event.evidence_code if latest_event else None),
                safe_detail=(latest_event.safe_detail if latest_event else None),
            )

    def consume_retry(self, action_id: UUID | str) -> ActionRecord:
        with self._session_factory.begin() as session:
            row = session.get(UnsubscribeActionORM, str(action_id))
            if row is None:
                raise KeyError(str(action_id))
            if row.retry_count >= 1:
                raise ValueError("The reviewed retry allowance has already been used")
            row.retry_count += 1
            row.updated_at = datetime.now(UTC)
        updated = self.get(UUID(str(action_id)))
        assert updated is not None
        return updated

    def list_events(
        self,
        plan_id: UUID | str,
        *,
        after_event_id: str | None = None,
    ) -> tuple[ActionEventRecord, ...]:
        with self._session_factory() as session:
            statement = (
                select(ActionEventORM)
                .join(
                    UnsubscribeActionORM,
                    UnsubscribeActionORM.id == ActionEventORM.action_id,
                )
                .where(UnsubscribeActionORM.plan_id == str(plan_id))
            )
            if after_event_id is not None:
                try:
                    anchor_sequence = int(after_event_id)
                except ValueError as error:
                    raise KeyError(after_event_id) from error
                anchor = session.scalar(
                    select(ActionEventORM)
                    .join(
                        UnsubscribeActionORM,
                        UnsubscribeActionORM.id == ActionEventORM.action_id,
                    )
                    .where(
                        ActionEventORM.stream_sequence == anchor_sequence,
                        UnsubscribeActionORM.plan_id == str(plan_id),
                    )
                )
                if anchor is None:
                    raise KeyError(after_event_id)
                statement = statement.where(ActionEventORM.stream_sequence > anchor.stream_sequence)
            rows = session.scalars(statement.order_by(ActionEventORM.stream_sequence))
            return tuple(
                ActionEventRecord(
                    id=str(row.stream_sequence),
                    action_id=row.action_id,
                    state=ActionState(row.to_state),
                    evidence_code=row.evidence_code,
                    safe_detail=row.safe_detail,
                    created_at=_as_utc(row.created_at),
                )
                for row in rows
            )

    def set_state(
        self,
        action_id: UUID | str,
        state: ActionState,
        *,
        evidence_code: str,
        safe_detail: str,
        external_id: str | None = None,
    ) -> ActionRecord:
        with self._session_factory.begin() as session:
            row = session.get(UnsubscribeActionORM, str(action_id))
            if row is None:
                raise KeyError(str(action_id))
            previous = row.state
            transition_action(ActionState(previous), state)
            row.state = state.value
            row.external_id = external_id
            row.updated_at = datetime.now(UTC)
            sequence = session.scalar(
                select(func.count(ActionEventORM.id)).where(
                    ActionEventORM.action_id == str(action_id)
                )
            )
            session.add(
                ActionEventORM(
                    action_id=str(action_id),
                    sequence=int(sequence or 0) + 1,
                    from_state=previous,
                    to_state=state.value,
                    evidence_code=evidence_code,
                    safe_detail=safe_detail,
                )
            )
        updated = self.get(UUID(str(action_id)))
        assert updated is not None
        return updated

    def persist_outbound_message_id(self, action_id: str, message_id: str) -> None:
        with self._session_factory.begin() as session:
            row = session.get(UnsubscribeActionORM, action_id)
            if row is None:
                raise KeyError(action_id)
            if row.outbound_message_id not in (None, message_id):
                raise ValueError("The action already has a different outbound message ID")
            row.outbound_message_id = message_id
            row.updated_at = datetime.now(UTC)

    def get(self, action_id: UUID) -> ActionRecord | None:
        with self._session_factory() as session:
            row = session.get(UnsubscribeActionORM, str(action_id))
            if row is None:
                return None
            return self._from_row(row)

    def get_by_idempotency_key(self, idempotency_key: str) -> ActionRecord | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(UnsubscribeActionORM).where(
                    UnsubscribeActionORM.idempotency_key == idempotency_key
                )
            )
            return self._from_row(row) if row is not None else None

    @staticmethod
    def _to_row(action: ActionRecord) -> UnsubscribeActionORM:
        return UnsubscribeActionORM(
            id=str(action.id),
            plan_id=str(action.plan_id),
            candidate_id=str(action.candidate_id),
            idempotency_key=action.idempotency_key,
            method=action.method.value,
            state=action.state.value,
            encrypted_payload=action.encrypted_payload,
            display_sender=action.display_sender,
            display_subject=action.display_subject,
            target_display=action.target_display,
            retry_count=action.retry_count,
            outbound_message_id=action.outbound_message_id,
            external_id=action.external_id,
            created_at=action.created_at,
            updated_at=action.updated_at,
        )

    @staticmethod
    def _from_row(row: UnsubscribeActionORM) -> ActionRecord:
        return ActionRecord(
            id=UUID(row.id),
            plan_id=UUID(row.plan_id),
            candidate_id=UUID(row.candidate_id),
            idempotency_key=row.idempotency_key,
            method=UnsubscribeMethod(row.method),
            state=ActionState(row.state),
            encrypted_payload=row.encrypted_payload,
            display_sender=row.display_sender,
            display_subject=row.display_subject,
            target_display=row.target_display,
            retry_count=row.retry_count,
            outbound_message_id=row.outbound_message_id,
            external_id=row.external_id,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
        )

    def _list_for_plan(self, session: Session, plan_id: str) -> tuple[ActionRecord, ...]:
        rows = session.scalars(
            select(UnsubscribeActionORM)
            .where(UnsubscribeActionORM.plan_id == plan_id)
            .order_by(UnsubscribeActionORM.created_at, UnsubscribeActionORM.id)
        )
        return tuple(self._from_row(row) for row in rows)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
