from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.actions.planner import ActionPlanService, PlanSelection
from app.candidates.grouper import EvaluatedMessage
from app.domain.models import ClassificationCategory, UnsubscribeMethod
from app.email_processing.unsubscribe import DiscoveredMethod
from app.pipeline import InMemoryCandidateCatalog
from app.security.payload_crypto import PayloadCipher, PayloadKeyUnavailable


class AcceptingPolicy:
    async def validate_at_plan_time(self, target: str):
        return type("Validated", (), {"url": target, "origin": "https://example.com"})()


def catalog_for(method: UnsubscribeMethod, target: str) -> InMemoryCandidateCatalog:
    catalog = InMemoryCandidateCatalog()
    catalog.add(
        EvaluatedMessage(
            gmail_id="m1",
            sender="Brief <brief@example.com>",
            subject="Weekly brief",
            sent_at=datetime(2026, 9, 1, tzinfo=UTC),
            list_id="brief.example.com",
            category=ClassificationCategory.MARKETING,
            confidence=0.9,
            methods=(DiscoveredMethod(method, target, "header"),),
        )
    )
    return catalog


async def test_mailto_plan_contains_exact_bounded_preview() -> None:
    catalog = catalog_for(
        UnsubscribeMethod.MAILTO,
        "mailto:leave@example.com?subject=Remove%20me&body=Please%20unsubscribe%20me",
    )
    candidate = catalog.candidates()[0]

    plan = await ActionPlanService(catalog, url_policy=AcceptingPolicy()).create(
        [PlanSelection(candidate.id, candidate.revision)]
    )

    assert plan.items[0].mail_draft is not None
    assert plan.items[0].mail_draft.recipient == "leave@example.com"
    assert plan.items[0].mail_draft.subject == "Remove me"
    assert plan.items[0].mail_draft.body == "Please unsubscribe me"
    assert "mailto:" not in plan.items[0].target_display


async def test_repeated_review_creates_a_fresh_consent_snapshot() -> None:
    catalog = catalog_for(UnsubscribeMethod.RFC8058, "https://example.com/unsubscribe")
    candidate = catalog.candidates()[0]
    service = ActionPlanService(catalog, url_policy=AcceptingPolicy())

    first = await service.create([PlanSelection(candidate.id, candidate.revision)])
    second = await service.create([PlanSelection(candidate.id, candidate.revision)])

    assert first.id != second.id
    assert first.digest == second.digest


@pytest.mark.parametrize(
    "target",
    [
        "mailto:one@example.com,two@example.com",
        "mailto:leave@example.com?subject=ok%0ABcc%3Aattacker%40example.com",
        "mailto:not-an-address",
    ],
)
async def test_mailto_plan_rejects_ambiguous_or_injected_draft(target: str) -> None:
    catalog = catalog_for(UnsubscribeMethod.MAILTO, target)
    candidate = catalog.candidates()[0]

    with pytest.raises(ValueError):
        await ActionPlanService(catalog).create([PlanSelection(candidate.id, candidate.revision)])


def test_payload_cipher_uses_unique_nonces_and_action_bound_aad() -> None:
    cipher = PayloadCipher(b"k" * 32)
    action_id = uuid4()
    payload = {"version": 1, "method": "rfc8058", "target": "https://example.com/u?t=x"}

    first = cipher.encrypt(action_id, payload)
    second = cipher.encrypt(action_id, payload)

    assert first != second
    assert cipher.decrypt(action_id, first) == payload
    with pytest.raises(ValueError):
        cipher.decrypt(uuid4(), first)
    assert b"example.com" not in first


def test_payload_cipher_fails_closed_when_secure_store_is_unavailable() -> None:
    class UnavailableStore:
        def get(self, key: str) -> str | None:
            raise RuntimeError("locked")

        def set(self, key: str, value: str) -> None:
            raise AssertionError("must not replace an unreadable key")

        def delete(self, key: str) -> None:
            pass

    with pytest.raises(PayloadKeyUnavailable):
        PayloadCipher.from_credential_store(UnavailableStore())
