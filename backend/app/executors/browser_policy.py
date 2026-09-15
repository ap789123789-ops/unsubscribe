import re
from dataclasses import dataclass

from app.domain.state_machine import ActionState

RULE_VERSION = "browser-outcome-en-v1"
POSITIVE_PATTERNS = (
    re.compile(r"\byou (?:have been|are now) unsubscribed\b", re.I),
    re.compile(r"\bemail preferences (?:have been )?updated\b", re.I),
    re.compile(r"\bunsubscription (?:was )?successful\b", re.I),
)
NEGATIVE_PATTERNS = (
    re.compile(r"\bcould not (?:unsubscribe|update)\b", re.I),
    re.compile(r"\bunable to (?:unsubscribe|update)\b", re.I),
    re.compile(r"\bnot unsubscribed\b", re.I),
    re.compile(r"\b(?:link|request) (?:has )?expired\b", re.I),
    re.compile(r"\berror\b", re.I),
)


@dataclass(frozen=True)
class BrowserOutcome:
    state: ActionState
    evidence_code: str
    safe_detail: str
    rule_version: str = RULE_VERSION


class BrowserOutcomePolicy:
    def evaluate(self, text: str, *, final_click_issued: bool) -> BrowserOutcome:
        normalized = " ".join(text.split())[:100_000]
        if final_click_issued:
            for pattern in NEGATIVE_PATTERNS:
                if pattern.search(normalized):
                    return BrowserOutcome(
                        state=ActionState.FAILED,
                        evidence_code="browser_explicit_error_v1",
                        safe_detail="The page explicitly reported that the request failed.",
                    )
        for pattern in POSITIVE_PATTERNS:
            if pattern.search(normalized):
                return BrowserOutcome(
                    state=ActionState.CONFIRMED,
                    evidence_code="browser_semantic_acceptance_v1",
                    safe_detail="The page explicitly acknowledged the unsubscribe request.",
                )
        if final_click_issued:
            return BrowserOutcome(
                state=ActionState.SUBMITTED,
                evidence_code="browser_click_submitted",
                safe_detail=(
                    "The final control was used, but completion was not explicitly confirmed."
                ),
            )
        return BrowserOutcome(
            state=ActionState.NEEDS_USER,
            evidence_code="browser_outcome_unresolved",
            safe_detail="The page does not yet show an explicit unsubscribe result.",
        )
