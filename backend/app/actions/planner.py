import asyncio
import hashlib
import hmac
import json
import re
from dataclasses import dataclass, replace
from email.utils import parseaddr
from typing import Protocol
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from app.domain.models import UnsubscribeMethod
from app.pipeline import InMemoryCandidateCatalog, StaleCandidate
from app.security.url_policy import ValidatedTarget


class PlanTargetPolicy(Protocol):
    async def validate_at_plan_time(self, target: str) -> ValidatedTarget: ...


@dataclass(frozen=True)
class ExactMailDraft:
    recipient: str
    subject: str
    body: str


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
    validated_target: ValidatedTarget | None = None
    mail_draft: ExactMailDraft | None = None


@dataclass(frozen=True)
class ActionPlan:
    id: str
    digest: str
    items: tuple[PlannedAction, ...]
    confirmed: bool = False


class PlanDigestMismatch(ValueError):
    pass


class ActionPlanService:
    def __init__(
        self,
        catalog: InMemoryCandidateCatalog,
        *,
        url_policy: PlanTargetPolicy | None = None,
    ) -> None:
        self._catalog = catalog
        self._url_policy = url_policy
        self._plans: dict[str, ActionPlan] = {}
        self._confirmation_lock = asyncio.Lock()

    async def create(self, selections: list[PlanSelection]) -> ActionPlan:
        if not selections:
            raise ValueError("Select at least one subscription")
        if len({item.candidate_id for item in selections}) != len(selections):
            raise ValueError("A subscription may be selected only once")
        items: list[PlannedAction] = []
        digest_items: list[dict[str, object]] = []
        for selection in selections:
            candidate = self._catalog.get(selection.candidate_id)
            if candidate is None:
                raise KeyError(selection.candidate_id)
            if candidate.revision != selection.revision:
                raise StaleCandidate(selection.candidate_id)
            target = candidate.method.target
            validated_target: ValidatedTarget | None = None
            mail_draft: ExactMailDraft | None = None
            if candidate.method.method is UnsubscribeMethod.MAILTO:
                mail_draft = exact_mail_draft(target)
            elif candidate.method.method in {
                UnsubscribeMethod.RFC8058,
                UnsubscribeMethod.BROWSER,
            }:
                if self._url_policy is not None:
                    validated_target = await self._url_policy.validate_at_plan_time(target)
            else:
                raise ValueError("The selected candidate has no unsubscribe method")
            item = PlannedAction(
                candidate_id=candidate.id,
                revision=candidate.revision,
                sender=candidate.sender,
                subject=candidate.representative_subject,
                method=candidate.method.method,
                target_display=display_target(candidate.method.method, target),
                target=target,
                validated_target=validated_target,
                mail_draft=mail_draft,
            )
            items.append(item)
            digest_items.append(digest_item(item))
        digest = hashlib.sha256(
            json.dumps(digest_items, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        existing = next(
            (candidate for candidate in self._plans.values() if candidate.digest == digest),
            None,
        )
        if existing is not None:
            return existing
        plan = ActionPlan(id=str(uuid4()), digest=digest, items=tuple(items))
        self._plans[plan.id] = plan
        return plan

    def get(self, plan_id: str) -> ActionPlan | None:
        return self._plans.get(plan_id)

    async def confirm(self, plan_id: str, digest: str) -> tuple[ActionPlan, bool]:
        async with self._confirmation_lock:
            plan = self.get(plan_id)
            if plan is None:
                raise KeyError(plan_id)
            if not hmac.compare_digest(plan.digest, digest):
                raise PlanDigestMismatch("The confirmation does not match the reviewed plan")
            for item in plan.items:
                candidate = self._catalog.get(item.candidate_id)
                if candidate is None or candidate.revision != item.revision:
                    raise StaleCandidate(item.candidate_id)
            if plan.confirmed:
                return plan, False
            confirmed = replace(plan, confirmed=True)
            self._plans[plan.id] = confirmed
            return confirmed, True


def digest_item(item: PlannedAction) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": item.candidate_id,
        "revision": item.revision,
        "method": item.method.value,
        "target": item.target,
    }
    if item.mail_draft is not None:
        payload["mail"] = {
            "recipient": item.mail_draft.recipient,
            "subject": item.mail_draft.subject,
            "body": item.mail_draft.body,
        }
    return payload


def exact_mail_draft(target: str) -> ExactMailDraft:
    parsed = urlsplit(target)
    if parsed.scheme.lower() != "mailto" or parsed.netloc or parsed.fragment:
        raise ValueError("The mail unsubscribe target is invalid")
    recipient = unquote(parsed.path).strip()
    if any(character in recipient for character in "\r\n,;"):
        raise ValueError("V1 requires exactly one mail unsubscribe recipient")
    _, parsed_address = parseaddr(recipient)
    if parsed_address != recipient or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", recipient):
        raise ValueError("The mail unsubscribe recipient is invalid")
    query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=10)
    unsupported = set(query) - {"subject", "body"}
    if unsupported or any(len(values) != 1 for values in query.values()):
        raise ValueError("The mail unsubscribe draft contains unsupported fields")
    subject = query.get("subject", ["Unsubscribe"])[0]
    body = query.get("body", ["Please unsubscribe me from this mailing list."])[0]
    if any(character in subject for character in "\r\n"):
        raise ValueError("The mail unsubscribe subject contains a line break")
    if not subject or len(subject) > 998 or len(body) > 20_000:
        raise ValueError("The mail unsubscribe draft exceeds its safety limits")
    return ExactMailDraft(recipient=recipient, subject=subject, body=body)


def display_target(method: UnsubscribeMethod, target: str) -> str:
    parsed = urlsplit(target)
    if method is UnsubscribeMethod.MAILTO:
        return exact_mail_draft(target).recipient
    return parsed.hostname or "Unknown destination"
