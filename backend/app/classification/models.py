from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import ClassificationCategory
from app.email_processing.normalizer import NormalizedEmail


class ClassificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ClassificationCategory
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=240)
    evidence_quote: str = Field(min_length=1, max_length=300)
    is_subscription: bool


class ClassificationResult(ClassificationOutput):
    source: str


class ClassifierModel(Protocol):
    async def classify(self, email: NormalizedEmail) -> ClassificationOutput: ...

