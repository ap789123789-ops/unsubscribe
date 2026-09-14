from datetime import UTC, datetime

from app.candidates.grouper import CandidateGrouper, EvaluatedMessage, SubscriptionCandidate
from app.classification.models import ClassifierModel
from app.classification.service import ClassificationService
from app.email_processing.normalizer import EmailNormalizer
from app.email_processing.unsubscribe import UnsubscribeDiscovery
from app.gmail.protocols import GmailMessage


class InMemoryCandidateCatalog:
    def __init__(self) -> None:
        self._messages: dict[str, EvaluatedMessage] = {}
        self._grouper = CandidateGrouper()

    def add(self, message: EvaluatedMessage) -> None:
        self._messages[message.gmail_id] = message

    def candidates(self) -> tuple[SubscriptionCandidate, ...]:
        return self._grouper.group(list(self._messages.values()))


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
