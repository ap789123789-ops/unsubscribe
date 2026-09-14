from dataclasses import replace
from datetime import UTC, datetime

from app.candidates.grouper import CandidateGrouper, EvaluatedMessage, SubscriptionCandidate
from app.classification.models import ClassifierModel
from app.classification.service import ClassificationService
from app.domain.models import ClassificationCategory
from app.email_processing.normalizer import EmailNormalizer
from app.email_processing.unsubscribe import UnsubscribeDiscovery
from app.gmail.protocols import GmailMessage


class InMemoryCandidateCatalog:
    def __init__(self) -> None:
        self._messages: dict[str, EvaluatedMessage] = {}
        self._grouper = CandidateGrouper()
        self._corrections: dict[str, tuple[int, ClassificationCategory]] = {}

    def add(self, message: EvaluatedMessage) -> None:
        self._messages[message.gmail_id] = message

    def candidates(self) -> tuple[SubscriptionCandidate, ...]:
        candidates = self._grouper.group(list(self._messages.values()))
        corrected: list[SubscriptionCandidate] = []
        for candidate in candidates:
            correction = self._corrections.get(candidate.id)
            if correction is None:
                corrected.append(candidate)
                continue
            revision, category = correction
            corrected.append(replace(candidate, revision=revision, category=category))
        return tuple(corrected)

    def get(self, candidate_id: str) -> SubscriptionCandidate | None:
        return next(
            (candidate for candidate in self.candidates() if candidate.id == candidate_id),
            None,
        )

    def correct(
        self,
        candidate_id: str,
        expected_revision: int,
        category: ClassificationCategory,
    ) -> SubscriptionCandidate:
        candidate = self.get(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        if candidate.revision != expected_revision:
            raise StaleCandidate(candidate_id)
        self._corrections[candidate_id] = (candidate.revision + 1, category)
        corrected = self.get(candidate_id)
        assert corrected is not None
        return corrected


class StaleCandidate(RuntimeError):
    pass


class ProcessingPipeline:
    def __init__(self, model: ClassifierModel, catalog: InMemoryCandidateCatalog) -> None:
        self._normalizer = EmailNormalizer()
        self._discovery = UnsubscribeDiscovery()
        self._classification = ClassificationService(model)
        self._catalog = catalog

    async def process(self, message: GmailMessage) -> None:
        email = self._normalizer.normalize(message)
        methods = self._discovery.discover(email)
        classification = await self._classification.classify(email)
        sent_at = (
            datetime.fromtimestamp(message.internal_date_ms / 1000, tz=UTC)
            if message.internal_date_ms is not None
            else datetime.now(UTC)
        )
        self._catalog.add(
            EvaluatedMessage(
                gmail_id=message.id,
                sender=email.headers.get("from", "Unknown sender"),
                subject=email.headers.get("subject", "(no subject)"),
                sent_at=sent_at,
                list_id=email.headers.get("list-id"),
                category=classification.category,
                confidence=classification.confidence,
                methods=methods,
                reason=classification.reason,
                evidence_quote=classification.evidence_quote,
            )
        )

    async def __call__(self, message: GmailMessage) -> None:
        await self.process(message)
