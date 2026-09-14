import asyncio
import hashlib
import json
from uuid import NAMESPACE_URL, UUID, uuid5

from app.actions.planner import ActionPlan, ActionPlanService, PlannedAction
from app.domain.models import ActionRecord, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.executors.mailto import MailtoExecutor, SendAuthorizationRequired
from app.executors.models import ExecutionResult, MailtoPayload, Rfc8058Payload
from app.executors.rfc8058 import Rfc8058Executor
from app.persistence.repositories import ActionRepository
from app.security.payload_crypto import PayloadCipher


class ExecutionUnavailable(RuntimeError):
    pass


class ExecutionCoordinator:
    def __init__(
        self,
        *,
        plans: ActionPlanService,
        repository: ActionRepository,
        cipher: PayloadCipher,
        rfc8058: Rfc8058Executor,
        mailto: MailtoExecutor,
    ) -> None:
        self._plans = plans
        self._repository = repository
        self._cipher = cipher
        self._rfc8058 = rfc8058
        self._mailto = mailto
        self._lock = asyncio.Lock()

    async def confirm_and_execute(
        self, plan_id: str, digest: str
    ) -> tuple[ActionRecord, ...]:
        async with self._lock:
            pending = self._plans.get(plan_id)
            if pending is None:
                raise KeyError(plan_id)
            if any(
                item.method is UnsubscribeMethod.MAILTO for item in pending.items
            ) and not await self._mailto.is_authorized():
                raise SendAuthorizationRequired(
                    "Gmail send permission is required before confirmation"
                )
            plan, newly_confirmed = await self._plans.confirm(plan_id, digest)
            if not newly_confirmed:
                return self._repository.list_for_plan(plan.id)
            actions = tuple(self._build_action(plan, item) for item in plan.items)
            self._repository.create_confirmed_plan(plan, actions)
            results: list[ActionRecord] = []
            for action, item in zip(actions, plan.items, strict=True):
                self._repository.set_state(
                    action.id,
                    ActionState.EXECUTING,
                    evidence_code="execution_started",
                    safe_detail=f"Started the reviewed {item.method.value} action.",
                )
                if item.method is UnsubscribeMethod.RFC8058:
                    if item.validated_target is None:
                        raise ExecutionUnavailable("The RFC target was not safety-validated")
                    result = await self._rfc8058.execute(
                        Rfc8058Payload(target=item.validated_target)
                    )
                elif item.method is UnsubscribeMethod.MAILTO:
                    if item.mail_draft is None:
                        raise ExecutionUnavailable("The mail draft is unavailable")
                    try:
                        result = await self._mailto.execute(
                            str(action.id), MailtoPayload(draft=item.mail_draft)
                        )
                    except SendAuthorizationRequired:
                        result = ExecutionResult(
                            state=ActionState.NEEDS_USER,
                            evidence_code="gmail_send_authorization_required",
                            safe_detail="Gmail send permission is no longer available.",
                        )
                else:
                    result = ExecutionResult(
                        state=ActionState.NEEDS_USER,
                        evidence_code="browser_executor_pending",
                        safe_detail="This website action requires the isolated browser step.",
                    )
                results.append(
                    self._repository.set_state(
                        action.id,
                        result.state,
                        evidence_code=result.evidence_code,
                        safe_detail=result.safe_detail,
                        external_id=result.external_id,
                    )
                )
            return tuple(results)

    def _build_action(self, plan: ActionPlan, item: PlannedAction) -> ActionRecord:
        action_id = uuid5(NAMESPACE_URL, f"{plan.id}:{item.candidate_id}:{item.revision}")
        payload: dict[str, object]
        if item.method is UnsubscribeMethod.MAILTO:
            assert item.mail_draft is not None
            payload = {
                "version": 1,
                "method": item.method.value,
                "recipient": item.mail_draft.recipient,
                "subject": item.mail_draft.subject,
                "body": item.mail_draft.body,
            }
        else:
            payload = {"version": 1, "method": item.method.value, "target": item.target}
        idempotency_key = hashlib.sha256(
            json.dumps(
                {
                    "plan": plan.id,
                    "candidate": item.candidate_id,
                    "revision": item.revision,
                    "method": item.method.value,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return ActionRecord(
            id=action_id,
            plan_id=UUID(plan.id),
            candidate_id=UUID(item.candidate_id),
            idempotency_key=idempotency_key,
            method=item.method,
            state=ActionState.CONFIRMED_BY_USER,
            encrypted_payload=self._cipher.encrypt(action_id, payload),
        )
