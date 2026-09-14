import hashlib
import json
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from app.domain.models import UnsubscribeMethod
from app.pipeline import InMemoryCandidateCatalog, StaleCandidate


@dataclass(frozen=True)
class PlanSelection:
    candidate_id: str
    revision: int


@dataclass(frozen=True)
class PlannedAction:
    candidate_id: str
    revision: int
    sender: str
    subject: str
    method: UnsubscribeMethod
    target_display: str
    target: str


@dataclass(frozen=True)
class ActionPlan:
    id: str
    digest: str
    items: tuple[PlannedAction, ...]
    confirmed: bool = False


class ActionPlanService:
    def __init__(self, catalog: InMemoryCandidateCatalog) -> None:
        self._catalog = catalog
        self._plans: dict[str, ActionPlan] = {}

    def create(self, selections: list[PlanSelection]) -> ActionPlan:
        if not selections:
            raise ValueError("Select at least one subscription")
        items: list[PlannedAction] = []
        digest_items: list[dict[str, object]] = []
        for selection in selections:
            candidate = self._catalog.get(selection.candidate_id)
            if candidate is None:
                raise KeyError(selection.candidate_id)
            if candidate.revision != selection.revision:
                raise StaleCandidate(selection.candidate_id)
            target = candidate.method.target
            items.append(
                PlannedAction(
                    candidate_id=candidate.id,
                    revision=candidate.revision,
                    sender=candidate.sender,
                    subject=candidate.representative_subject,
                    method=candidate.method.method,
                    target_display=display_target(candidate.method.method, target),
                    target=target,
                )
            )
            digest_items.append(
                {
                    "candidate_id": candidate.id,
                    "revision": candidate.revision,
                    "method": candidate.method.method.value,
                    "target": target,
                }
            )
        digest = hashlib.sha256(
            json.dumps(digest_items, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        plan = ActionPlan(id=str(uuid4()), digest=digest, items=tuple(items))
        self._plans[plan.id] = plan
        return plan

    def get(self, plan_id: str) -> ActionPlan | None:
        return self._plans.get(plan_id)


def display_target(method: UnsubscribeMethod, target: str) -> str:
    parsed = urlsplit(target)
    if method is UnsubscribeMethod.MAILTO:
        recipient = parsed.path
        subject = parse_qs(parsed.query).get("subject", [""])[0]
        return f"{recipient} — {subject}" if subject else recipient
    return parsed.hostname or "Unknown destination"

