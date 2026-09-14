from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


def uuid_string() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class AccountORM(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    scopes: Mapped[str] = mapped_column(Text, default="")
    credential_ref: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScanJobORM(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    query: Mapped[str] = mapped_column(String(500))
    max_messages: Mapped[int] = mapped_column(Integer)
    next_page_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScanCheckpointORM(Base):
    __tablename__ = "scan_checkpoints"

    scan_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    next_page_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    seen_message_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    completed: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageORM(Base):
    __tablename__ = "messages"

    gmail_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scan_jobs.id"))
    thread_id: Mapped[str] = mapped_column(String(255))
    sender_address: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    list_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body_hash: Mapped[str] = mapped_column(String(64))
    safe_excerpt: Mapped[str] = mapped_column(Text)


class ClassificationORM(Base):
    __tablename__ = "classifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    gmail_id: Mapped[str] = mapped_column(ForeignKey("messages.gmail_id"))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float)
    reason_evidence_json: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40))


class SubscriptionCandidateORM(Base):
    __tablename__ = "subscription_candidates"
    __table_args__ = (UniqueConstraint("grouping_key", "revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    grouping_key: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(40))
    method: Mapped[str] = mapped_column(String(40))
    sanitized_target: Mapped[str] = mapped_column(Text)


class CandidateMessageORM(Base):
    __tablename__ = "candidate_messages"

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("subscription_candidates.id"), primary_key=True
    )
    gmail_id: Mapped[str] = mapped_column(ForeignKey("messages.gmail_id"), primary_key=True)


class ActionPlanORM(Base):
    __tablename__ = "action_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UnsubscribeActionORM(Base):
    __tablename__ = "unsubscribe_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("action_plans.id"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("subscription_candidates.id"))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    method: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(40))
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    outbound_message_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActionEventORM(Base):
    __tablename__ = "action_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    action_id: Mapped[str] = mapped_column(ForeignKey("unsubscribe_actions.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    from_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_state: Mapped[str] = mapped_column(String(40))
    evidence_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    safe_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
