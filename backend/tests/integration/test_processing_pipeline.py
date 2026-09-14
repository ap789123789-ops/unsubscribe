import base64

from app.classification.models import ClassificationOutput
from app.domain.models import ClassificationCategory, UnsubscribeMethod
from app.gmail.protocols import GmailMessage
from app.pipeline import InMemoryCandidateCatalog, ProcessingPipeline


class MarketingModel:
    async def classify(self, email):
        return ClassificationOutput(
            category=ClassificationCategory.MARKETING,
            confidence=0.93,
            reason="Recurring editorial newsletter",
            evidence_quote="Weekly product brief",
            is_subscription=True,
        )


async def test_pipeline_turns_full_gmail_message_into_subscription_candidate() -> None:
    body = base64.urlsafe_b64encode(b"Weekly product brief and offers").decode().rstrip("=")
    message = GmailMessage(
        id="m1",
        thread_id="t1",
        size_estimate=100,
        internal_date_ms=1_757_000_000_000,
        payload={
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "Brief <brief@example.com>"},
                {"name": "Subject", "value": "Weekly product brief"},
                {"name": "List-ID", "value": "brief.example.com"},
                {
                    "name": "List-Unsubscribe",
                    "value": "<https://example.com/unsubscribe?token=secret>",
                },
                {"name": "List-Unsubscribe-Post", "value": "List-Unsubscribe=One-Click"},
            ],
            "body": {"data": body},
        },
    )
    catalog = InMemoryCandidateCatalog()
    pipeline = ProcessingPipeline(MarketingModel(), catalog)

    await pipeline.process(message)
    candidate = catalog.candidates()[0]

    assert candidate.category is ClassificationCategory.MARKETING
    assert candidate.method.method is UnsubscribeMethod.RFC8058
    assert candidate.message_ids == ("m1",)
