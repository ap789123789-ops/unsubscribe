from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.classification.models import ClassificationOutput
from app.classification.openai_agent import OpenAIAgentsClassifier
from app.domain.models import ClassificationCategory
from app.email_processing.normalizer import NormalizedEmail


async def test_classifier_reserves_output_budget_for_reasoning_and_structured_output(
    monkeypatch,
) -> None:
    runner = AsyncMock(
        return_value=SimpleNamespace(
            final_output=ClassificationOutput(
                category=ClassificationCategory.MARKETING,
                confidence=0.95,
                reason="Promotional newsletter",
                evidence_quote="Weekly product news",
                is_subscription=True,
            )
        )
    )
    monkeypatch.setattr("app.classification.openai_agent.Runner.run", runner)
    email = NormalizedEmail(
        gmail_id="message-1",
        thread_id="thread-1",
        headers={"from": "news@example.com", "subject": "Weekly product news"},
        text="Weekly product news. Unsubscribe here.",
        model_text="Weekly product news. Unsubscribe here.",
        safe_excerpt="Weekly product news.",
        body_hash="a" * 64,
        links=(),
        oversized=False,
    )

    await OpenAIAgentsClassifier(api_key="test-key").classify(email)

    agent = runner.await_args.args[0]
    assert agent.model_settings.max_tokens == 1_200
    assert agent.model_settings.reasoning.effort == "low"
    assert agent.model_settings.verbosity == "low"
    assert agent.model_settings.store is False
