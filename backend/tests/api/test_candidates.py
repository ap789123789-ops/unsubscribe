from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.candidates.grouper import EvaluatedMessage
from app.domain.models import ClassificationCategory, UnsubscribeMethod
from app.email_processing.unsubscribe import DiscoveredMethod
from app.main import create_app
from app.pipeline import InMemoryCandidateCatalog


def catalog_with_candidate() -> InMemoryCandidateCatalog:
    catalog = InMemoryCandidateCatalog()
    catalog.add(
        EvaluatedMessage(
            gmail_id="m1",
            sender="Brief <brief@example.com>",
            subject="Weekly product brief",
            sent_at=datetime(2026, 9, 1, tzinfo=UTC),
            list_id="brief.example.com",
            category=ClassificationCategory.MARKETING,
            confidence=0.93,
            methods=(
                DiscoveredMethod(
                    UnsubscribeMethod.RFC8058,
                    "https://example.com/unsubscribe?token=private",
                    "header",
                ),
            ),
            reason="Recurring editorial newsletter",
            evidence_quote="Weekly product brief",
        )
    )
    return catalog


def local_client(app):
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    csrf = client.get("/api/session").json()["csrf_token"]
    return client, {"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": csrf}


def test_candidate_list_redacts_target_and_correction_creates_revision() -> None:
    catalog = catalog_with_candidate()
    client, headers = local_client(create_app(candidate_catalog=catalog))

    candidate = client.get("/api/candidates").json()["items"][0]

    assert candidate["category"] == "marketing"
    assert candidate["target_display"] == "example.com"
    assert "private" not in str(candidate)

    corrected = client.patch(
        f"/api/candidates/{candidate['id']}",
        headers=headers,
        json={"category": "unclear", "expected_revision": 1},
    )
    assert corrected.status_code == 200
    assert corrected.json()["revision"] == 2
    assert corrected.json()["category"] == "unclear"
