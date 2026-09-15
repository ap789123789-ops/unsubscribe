from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.state_machine import ActionState


class ClassificationCategory(StrEnum):
    MARKETING = "marketing"
    NON_MARKETING = "non_marketing"
    UNCLEAR = "unclear"


class UnsubscribeMethod(StrEnum):
    RFC8058 = "rfc8058"
    MAILTO = "mailto"
    BROWSER = "browser"
    NONE = "none"


class ActionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    plan_id: UUID
    candidate_id: UUID
    idempotency_key: str
    method: UnsubscribeMethod
    state: ActionState
    encrypted_payload: bytes
    display_sender: str = "Unknown sender"
    display_subject: str = "(no subject)"
    target_display: str = "Unknown destination"
    retry_count: int = Field(default=0, ge=0)
    outbound_message_id: str | None = None
    external_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
