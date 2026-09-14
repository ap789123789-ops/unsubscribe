from datetime import UTC, datetime

from app.candidates.grouper import EvaluatedMessage
from app.domain.models import ClassificationCategory, UnsubscribeMethod
from app.email_processing.unsubscribe import DiscoveredMethod
from app.main import create_app
from app.pipeline import InMemoryCandidateCatalog


def test_catalog() -> InMemoryCandidateCatalog:
    catalog = InMemoryCandidateCatalog()
    catalog.add(
        EvaluatedMessage(
            gmail_id="fixture-marketing-1",
            sender="Morning Brief <brief@example.com>",
            subject="This week in product",
            sent_at=datetime(2026, 9, 14, 12, tzinfo=UTC),
            list_id="brief.example.com",
            category=ClassificationCategory.MARKETING,
            confidence=0.93,
            methods=(
                DiscoveredMethod(
                    method=UnsubscribeMethod.RFC8058,
                    target="https://example.com/unsubscribe?token=private-fixture",
                    source="header",
                ),
            ),
            reason="Recurring editorial newsletter",
            evidence_quote="This week in product",
        )
    )
    catalog.add(
        EvaluatedMessage(
            gmail_id="fixture-unclear-1",
            sender="Community <hello@community.example>",
            subject="September update",
            sent_at=datetime(2026, 9, 12, 12, tzinfo=UTC),
            list_id="community.example",
            category=ClassificationCategory.UNCLEAR,
            confidence=0.52,
            methods=(
                DiscoveredMethod(
                    method=UnsubscribeMethod.BROWSER,
                    target="https://community.example/preferences?token=private-fixture",
                    source="header-or-body",
                ),
            ),
            reason="Mixed editorial and account content",
            evidence_quote="September update",
        )
    )
    catalog.add(
        EvaluatedMessage(
            gmail_id="fixture-mailto-1",
            sender="Mailing Club <club@example.net>",
            subject="Club dispatch",
            sent_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
            list_id="club.example.net",
            category=ClassificationCategory.MARKETING,
            confidence=0.88,
            methods=(
                DiscoveredMethod(
                    method=UnsubscribeMethod.MAILTO,
                    target=(
                        "mailto:leave@example.net?subject=Remove%20me"
                        "&body=Please%20unsubscribe%20this%20address"
                    ),
                    source="header",
                ),
            ),
            reason="Recurring mailing list dispatch",
            evidence_quote="Club dispatch",
        )
    )
    return catalog


app = create_app(candidate_catalog=test_catalog())
