from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr
from urllib.parse import urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

from app.domain.models import ClassificationCategory, UnsubscribeMethod
from app.email_processing.unsubscribe import DiscoveredMethod

METHOD_PRIORITY = {
    UnsubscribeMethod.RFC8058: 0,
    UnsubscribeMethod.MAILTO: 1,
    UnsubscribeMethod.BROWSER: 2,
    UnsubscribeMethod.NONE: 3,
}


@dataclass(frozen=True)
class EvaluatedMessage:
    gmail_id: str
    sender: str
    subject: str
    sent_at: datetime
    list_id: str | None
    category: ClassificationCategory
    confidence: float
    methods: tuple[DiscoveredMethod, ...]
    reason: str = ""
    evidence_quote: str = ""


@dataclass(frozen=True)
class SubscriptionCandidate:
    id: str
    revision: int
    grouping_key: str
    sender: str
    representative_subject: str
    message_ids: tuple[str, ...]
    category: ClassificationCategory
    confidence: float
    method: DiscoveredMethod
    first_seen: datetime
    last_seen: datetime
    reason: str
    evidence_quote: str


class CandidateGrouper:
    def group(self, messages: list[EvaluatedMessage]) -> tuple[SubscriptionCandidate, ...]:
        grouped: dict[str, list[EvaluatedMessage]] = {}
        for message in messages:
            if not message.methods:
                continue
            grouped.setdefault(self._key(message), []).append(message)

        candidates: list[SubscriptionCandidate] = []
        for key, members in sorted(grouped.items()):
            members.sort(key=lambda item: item.sent_at)
            categories = {member.category for member in members}
            category = (
                next(iter(categories))
                if len(categories) == 1
                else ClassificationCategory.UNCLEAR
            )
            methods = [method for member in members for method in member.methods]
            method = min(methods, key=lambda item: METHOD_PRIORITY[item.method])
            candidates.append(
                SubscriptionCandidate(
                    id=str(uuid5(NAMESPACE_URL, key)),
                    revision=1,
                    grouping_key=key,
                    sender=members[-1].sender,
                    representative_subject=members[-1].subject,
                    message_ids=tuple(member.gmail_id for member in members),
                    category=category,
                    confidence=min(member.confidence for member in members),
                    method=method,
                    first_seen=members[0].sent_at,
                    last_seen=members[-1].sent_at,
                    reason=members[-1].reason,
                    evidence_quote=members[-1].evidence_quote,
                )
            )
        return tuple(candidates)

    @staticmethod
    def _key(message: EvaluatedMessage) -> str:
        if message.list_id:
            normalized = message.list_id.strip().strip("<>").lower()
            return f"list:{normalized}"
        if message.methods:
            target = message.methods[0].target
            parsed = urlsplit(target)
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                endpoint = urlunsplit(
                    (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", "")
                )
                return f"endpoint:{endpoint}"
        address = parseaddr(message.sender)[1].lower()
        return f"sender:{address}"
