import pytest

from app.security.url_policy import UnsafeTarget, UrlSafetyPolicy


class SequenceResolver:
    def __init__(self, answers: list[tuple[str, ...]]) -> None:
        self.answers = answers
        self.calls = 0

    async def resolve(self, hostname: str) -> tuple[str, ...]:
        answer = self.answers[self.calls]
        self.calls += 1
        return answer


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/u",
        "https://user:secret@example.com/u",
        "https://127.0.0.1/u",
        "https://169.254.169.254/latest/meta-data",
        "https://example.com:8443/u",
    ],
)
async def test_automatic_request_rejects_unsafe_target(url: str) -> None:
    policy = UrlSafetyPolicy(resolver=SequenceResolver([("93.184.216.34",)]))

    with pytest.raises(UnsafeTarget):
        await policy.validate_at_plan_time(url)


async def test_all_dns_answers_must_be_public_and_target_is_rechecked() -> None:
    resolver = SequenceResolver(
        [
            ("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"),
            ("127.0.0.1",),
        ]
    )
    policy = UrlSafetyPolicy(resolver=resolver)

    target = await policy.validate_at_plan_time("https://Example.COM/unsubscribe?t=private")
    assert target.origin == "https://example.com"

    with pytest.raises(UnsafeTarget, match="public"):
        await policy.revalidate_before_connect(target)


async def test_mixed_public_and_private_dns_answers_are_rejected() -> None:
    policy = UrlSafetyPolicy(resolver=SequenceResolver([("93.184.216.34", "10.0.0.7")]))

    with pytest.raises(UnsafeTarget, match="public"):
        await policy.validate_at_plan_time("https://example.com/u")
