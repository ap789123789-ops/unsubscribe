import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.gmail.protocols import GmailGateway, GmailMessage


@dataclass(frozen=True)
class ScanRequest:
    scan_id: str
    days: int = 30
    max_messages: int = 500

    def __post_init__(self) -> None:
        if not 1 <= self.days <= 365:
            raise ValueError("days must be between 1 and 365")
        if not 1 <= self.max_messages <= 500:
            raise ValueError("max_messages must be between 1 and 500")


@dataclass(frozen=True)
class ScanResult:
    scan_id: str
    processed_count: int
    completed: bool


@dataclass(frozen=True)
class RehydrationResult:
    rehydrated: int
    failed: int


class ScanCheckpointStore(Protocol):
    def remember_request(self, request: ScanRequest) -> None: ...

    def incomplete_requests(self) -> tuple[ScanRequest, ...]: ...

    def seen_message_ids(self, scan_id: str) -> tuple[str, ...]: ...

    def page_token(self, scan_id: str) -> str | None: ...

    def has_seen(self, scan_id: str, message_id: str) -> bool: ...

    def mark_seen(self, scan_id: str, message_id: str) -> None: ...

    def checkpoint_page(self, scan_id: str, next_page_token: str | None) -> None: ...

    def count(self, scan_id: str) -> int: ...

    def is_complete(self, scan_id: str) -> bool: ...

    def complete(self, scan_id: str) -> None: ...


@dataclass
class InMemoryScanCheckpointStore:
    tokens: dict[str, str | None] = field(default_factory=dict)
    seen: dict[str, set[str]] = field(default_factory=dict)
    completed: set[str] = field(default_factory=set)
    page_tokens: list[str | None] = field(default_factory=list)
    requests: dict[str, ScanRequest] = field(default_factory=dict)

    def remember_request(self, request: ScanRequest) -> None:
        self.requests[request.scan_id] = request

    def incomplete_requests(self) -> tuple[ScanRequest, ...]:
        return tuple(
            request for scan_id, request in self.requests.items() if scan_id not in self.completed
        )

    def seen_message_ids(self, scan_id: str) -> tuple[str, ...]:
        return tuple(sorted(self.seen.get(scan_id, set())))

    def page_token(self, scan_id: str) -> str | None:
        return self.tokens.get(scan_id)

    def has_seen(self, scan_id: str, message_id: str) -> bool:
        return message_id in self.seen.get(scan_id, set())

    def mark_seen(self, scan_id: str, message_id: str) -> None:
        self.seen.setdefault(scan_id, set()).add(message_id)

    def checkpoint_page(self, scan_id: str, next_page_token: str | None) -> None:
        self.tokens[scan_id] = next_page_token
        self.page_tokens.append(next_page_token)

    def count(self, scan_id: str) -> int:
        return len(self.seen.get(scan_id, set()))

    def is_complete(self, scan_id: str) -> bool:
        return scan_id in self.completed

    def complete(self, scan_id: str) -> None:
        self.completed.add(scan_id)


class ScanService:
    def __init__(
        self,
        gateway: GmailGateway,
        checkpoints: ScanCheckpointStore,
        message_sink: Callable[[GmailMessage], object],
        *,
        retry_delays: tuple[float, ...] = (0, 0.05, 0.2),
    ) -> None:
        self._gateway = gateway
        self._checkpoints = checkpoints
        self._message_sink = message_sink
        self._retry_delays = retry_delays

    async def rehydrate(self, request: ScanRequest) -> RehydrationResult:
        """Rebuild transient review state from checkpointed Gmail message IDs."""
        rehydrated = 0
        failed = 0
        for message_id in self._checkpoints.seen_message_ids(request.scan_id):
            try:
                message = await self._read_with_retry(message_id)
                sink_result = self._message_sink(message)
                if inspect.isawaitable(sink_result):
                    await sink_result
            except Exception:  # noqa: BLE001 - one missing message must not block scan recovery
                failed += 1
                continue
            rehydrated += 1
        return RehydrationResult(rehydrated=rehydrated, failed=failed)

    async def run(self, request: ScanRequest) -> ScanResult:
        self._checkpoints.remember_request(request)
        if self._checkpoints.is_complete(request.scan_id):
            return ScanResult(request.scan_id, self._checkpoints.count(request.scan_id), True)

        page_token = self._checkpoints.page_token(request.scan_id)
        while self._checkpoints.count(request.scan_id) < request.max_messages:
            remaining = request.max_messages - self._checkpoints.count(request.scan_id)
            page = await self._gateway.list_messages(
                query=f"newer_than:{request.days}d",
                max_results=min(100, remaining),
                page_token=page_token,
            )
            for reference in page.messages:
                if self._checkpoints.has_seen(request.scan_id, reference.id):
                    continue
                message = await self._read_with_retry(reference.id)
                sink_result = self._message_sink(message)
                if inspect.isawaitable(sink_result):
                    await sink_result
                self._checkpoints.mark_seen(request.scan_id, reference.id)
                if self._checkpoints.count(request.scan_id) >= request.max_messages:
                    break

            self._checkpoints.checkpoint_page(request.scan_id, page.next_page_token)
            page_token = page.next_page_token
            if page_token is None:
                self._checkpoints.complete(request.scan_id)
                break

        return ScanResult(
            request.scan_id,
            self._checkpoints.count(request.scan_id),
            self._checkpoints.is_complete(request.scan_id),
        )

    async def _read_with_retry(self, message_id: str) -> GmailMessage:
        last_error: Exception | None = None
        for delay in self._retry_delays:
            if delay:
                await asyncio.sleep(delay)
            try:
                return await self._gateway.get_message(message_id)
            except Exception as error:  # noqa: BLE001 - boundary retry records final error
                last_error = error
        assert last_error is not None
        raise last_error
