import base64

from app.email_processing.normalizer import EmailNormalizer
from app.gmail.protocols import GmailMessage


def encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def test_normalizer_prefers_plain_text_and_removes_quoted_history() -> None:
    message = GmailMessage(
        id="m1",
        thread_id="t1",
        size_estimate=400,
        payload={
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "News <news@example.com>"},
                {"name": "Subject", "value": "Weekly brief"},
                {"name": "List-ID", "value": "Brief <brief.example.com>"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": encoded("Today’s brief\n\n> old quoted mail")},
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": encoded("<p>HTML fallback</p>")},
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "offer.pdf",
                    "body": {"data": encoded("private attachment")},
                },
            ],
        },
    )

    normalized = EmailNormalizer().normalize(message)

    assert normalized.text == "Today’s brief"
    assert normalized.headers["list-id"] == "Brief <brief.example.com>"
    assert "private attachment" not in normalized.text
    assert len(normalized.body_hash) == 64


def test_normalizer_safely_converts_html_and_obeys_model_budget() -> None:
    html = (
        '<p aria-hidden="true">tracking token</p><script>alert(1)</script>'
        '<p>Visible offer</p><a href="https://news.example/unsubscribe?id=secret">Unsubscribe</a>'
        + f"<p>{'x' * 30_000}</p>"
    )
    message = GmailMessage(
        id="m2",
        thread_id="t2",
        size_estimate=50_000,
        payload={
            "mimeType": "text/html",
            "headers": [{"name": "Subject", "value": "Offer"}],
            "body": {"data": encoded(html)},
        },
    )

    normalized = EmailNormalizer().normalize(message)

    assert "Visible offer" in normalized.text
    assert "alert(1)" not in normalized.text
    assert "tracking token" not in normalized.text
    assert normalized.links == ("https://news.example/unsubscribe?id=secret",)
    assert len(normalized.model_text) <= 20_100
    assert "[content truncated]" in normalized.model_text


def test_oversized_message_is_marked_for_abstention() -> None:
    message = GmailMessage(
        id="large",
        thread_id="t",
        size_estimate=10 * 1024 * 1024 + 1,
        payload={},
    )

    normalized = EmailNormalizer().normalize(message)

    assert normalized.oversized is True
    assert normalized.model_text == ""
