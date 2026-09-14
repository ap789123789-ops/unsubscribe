from app.domain.models import UnsubscribeMethod
from app.email_processing.normalizer import NormalizedEmail
from app.email_processing.unsubscribe import UnsubscribeDiscovery


def normalized(headers: dict[str, str], links: tuple[str, ...] = ()) -> NormalizedEmail:
    return NormalizedEmail(
        gmail_id="m1",
        thread_id="t1",
        headers=headers,
        text="message",
        model_text="message",
        safe_excerpt="message",
        body_hash="0" * 64,
        links=links,
        oversized=False,
    )


def test_discovers_one_click_before_mailto_and_body_link() -> None:
    result = UnsubscribeDiscovery().discover(
        normalized(
            {
                "list-unsubscribe": (
                    "<mailto:leave@example.com?subject=unsubscribe>, "
                    "<https://news.example/unsubscribe?token=secret>"
                ),
                "list-unsubscribe-post": "List-Unsubscribe=One-Click",
            },
            ("https://news.example/preferences",),
        )
    )

    assert [method.method for method in result] == [
        UnsubscribeMethod.RFC8058,
        UnsubscribeMethod.MAILTO,
        UnsubscribeMethod.BROWSER,
    ]
    assert result[0].target == "https://news.example/unsubscribe?token=secret"


def test_ignores_non_http_body_links() -> None:
    result = UnsubscribeDiscovery().discover(
        normalized({}, ("javascript:alert(1)", "https://example.com/account"))
    )

    assert result == ()
