from datetime import UTC, datetime

from app.candidates.grouper import CandidateGrouper, EvaluatedMessage
from app.domain.models import ClassificationCategory, UnsubscribeMethod
from app.email_processing.unsubscribe import DiscoveredMethod


def message(
    gmail_id: str,
    category: ClassificationCategory,
    *,
    list_id: str | None = "offers.example.com",
) -> EvaluatedMessage:
    return EvaluatedMessage(
        gmail_id=gmail_id,
        sender="Offers <offers@example.com>",
        subject=f"Offer {gmail_id}",
        sent_at=datetime(2026, 9, 1, tzinfo=UTC),
        list_id=list_id,
        category=category,
        confidence=0.9,
        methods=(
            DiscoveredMethod(
                UnsubscribeMethod.MAILTO,
                "mailto:leave@example.com",
                "header",
            ),
            DiscoveredMethod(
                UnsubscribeMethod.RFC8058,
                "https://example.com/one-click?token=secret",
                "header",
            ),
        ),
    )


def test_groups_by_list_id_and_prefers_one_click_method() -> None:
    candidates = CandidateGrouper().group(
        [
            message("m1", ClassificationCategory.MARKETING),
            message("m2", ClassificationCategory.MARKETING),
        ]
    )

    assert len(candidates) == 1
    assert candidates[0].grouping_key == "list:offers.example.com"
    assert candidates[0].message_ids == ("m1", "m2")
    assert candidates[0].method.method is UnsubscribeMethod.RFC8058


def test_conflicting_message_categories_make_candidate_unclear() -> None:
    candidate = CandidateGrouper().group(
        [
            message("m1", ClassificationCategory.MARKETING),
            message("m2", ClassificationCategory.NON_MARKETING),
        ]
    )[0]

    assert candidate.category is ClassificationCategory.UNCLEAR
