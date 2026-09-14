from app.classification.models import ClassificationResult, ClassifierModel
from app.classification.rules import RuleEngine
from app.domain.models import ClassificationCategory
from app.email_processing.normalizer import NormalizedEmail


class ClassificationService:
    def __init__(self, model: ClassifierModel, rules: RuleEngine | None = None) -> None:
        self._model = model
        self._rules = rules or RuleEngine()

    async def classify(self, email: NormalizedEmail) -> ClassificationResult:
        if email.oversized:
            return self._unclear("Message exceeds the safe processing limit", "size limit", "rule")
        protected = self._rules.protected_result(email)
        if protected is not None:
            return protected
        try:
            output = await self._model.classify(email)
        except Exception:  # noqa: BLE001 - model boundary safely abstains
            return self._unclear(
                "Model classification was unavailable",
                "unavailable",
                "model_error",
            )

        evidence_haystack = f"{email.headers.get('subject', '')}\n{email.model_text}".casefold()
        if output.confidence < 0.65 or output.evidence_quote.casefold() not in evidence_haystack:
            return self._unclear(
                "The classification lacked verifiable evidence",
                output.evidence_quote,
                "post_validation",
            )
        return ClassificationResult(**output.model_dump(), source="model")

    @staticmethod
    def _unclear(reason: str, evidence: str, source: str) -> ClassificationResult:
        return ClassificationResult(
            category=ClassificationCategory.UNCLEAR,
            confidence=0,
            reason=reason,
            evidence_quote=evidence,
            is_subscription=False,
            source=source,
        )
