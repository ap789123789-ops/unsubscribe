import re

from app.classification.models import ClassificationResult
from app.domain.models import ClassificationCategory
from app.email_processing.normalizer import NormalizedEmail

PROTECTED_PATTERNS = (
    r"security alert",
    r"new sign[- ]in",
    r"verification code",
    r"one[- ]time (?:code|password)",
    r"password reset",
    r"order (?:confirmation|shipped|delivered)",
    r"payment (?:received|failed)",
    r"invoice|receipt",
    r"appointment (?:confirmation|reminder)",
)


class RuleEngine:
    def protected_result(self, email: NormalizedEmail) -> ClassificationResult | None:
        haystack = f"{email.headers.get('subject', '')}\n{email.model_text}"
        for pattern in PROTECTED_PATTERNS:
            match = re.search(pattern, haystack, re.I)
            if match:
                return ClassificationResult(
                    category=ClassificationCategory.NON_MARKETING,
                    confidence=0.99,
                    reason="Protected transactional or security message",
                    evidence_quote=match.group(0),
                    is_subscription=False,
                    source="rule",
                )
        return None
