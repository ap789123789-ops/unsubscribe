from uuid import UUID

from app.domain.models import ActionRecord
from app.domain.state_machine import ActionState
from app.executors.browser import (
    BrowserExecutor,
    BrowserSessionRegistry,
    BrowserSessionSnapshot,
)
from app.persistence.repositories import ActionRepository


class BrowserSessionService:
    def __init__(
        self,
        *,
        executor: BrowserExecutor,
        registry: BrowserSessionRegistry,
        repository: ActionRepository,
    ) -> None:
        self._executor = executor
        self._registry = registry
        self._repository = repository

    def get(self, session_id: str) -> BrowserSessionSnapshot:
        return self._registry.get_snapshot(session_id)

    async def take_over(self, session_id: str) -> BrowserSessionSnapshot:
        return await self._executor.take_over(session_id)

    async def resume(self, session_id: str) -> ActionRecord:
        snapshot = self._registry.get_snapshot(session_id)
        self._repository.set_state(
            UUID(snapshot.action_id),
            ActionState.EXECUTING,
            evidence_code="user_resumed_browser",
            safe_detail="The user asked the guarded browser session to resume.",
        )
        result = await self._executor.resume(session_id)
        return self._repository.set_state(
            UUID(snapshot.action_id),
            result.state,
            evidence_code=result.evidence_code,
            safe_detail=result.safe_detail,
            external_id=result.external_id,
        )

    async def cancel(self, session_id: str) -> ActionRecord:
        snapshot = await self._executor.cancel(session_id)
        return self._repository.set_state(
            UUID(snapshot.action_id),
            ActionState.REVIEWED,
            evidence_code="user_stopped_browser",
            safe_detail="The user stopped the guarded browser action.",
        )
