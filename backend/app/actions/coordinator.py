import asyncio
import hashlib
import json
from uuid import NAMESPACE_URL, UUID, uuid5

from app.actions.planner import (
    ActionPlan,
    ActionPlanService,
    ExactMailDraft,
    PlannedAction,
    PlanTargetPolicy,
    digest_item,
)
from app.domain.models import ActionRecord, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.executors.browser import BrowserExecutor
from app.executors.mailto import MailtoExecutor, SendAuthorizationRequired
from app.executors.models import BrowserPayload, ExecutionResult, MailtoPayload, Rfc8058Payload
from app.executors.rfc8058 import Rfc8058Executor
from app.persistence.repositories import ActionRepository
from app.security.payload_crypto import PayloadCipher
from app.security.url_policy import UnsafeTarget


class ExecutionUnavailable(RuntimeError):
    pass


class ActionAlreadyAttempted(RuntimeError):
    pass


class ActionRetryNotAllowed(RuntimeError):
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
        browser: BrowserExecutor | None = None,
        url_policy: PlanTargetPolicy | None = None,
    ) -> None:
        self._plans = plans
        self._repository = repository
        self._cipher = cipher
        self._rfc8058 = rfc8058
        self._mailto = mailto
        self._browser = browser
        self._url_policy = url_policy
        self._lock = asyncio.Lock()

    async def confirm_and_execute(self, plan_id: str, digest: str) -> tuple[ActionRecord, ...]:
        async with self._lock:
            pending = self._plans.get(plan_id)
            if pending is None:
                raise KeyError(plan_id)
            if pending.confirmed:
                return self._repository.list_for_plan(pending.id)
            actions = tuple(self._build_action(pending, item) for item in pending.items)
            if any(
                self._repository.get_by_idempotency_key(action.idempotency_key) is not None
                for action in actions
            ):
                raise ActionAlreadyAttempted(
                    "An unchanged version of this unsubscribe action was already attempted."
                )
            if (
                any(item.method is UnsubscribeMethod.MAILTO for item in pending.items)
                and not await self._mailto.is_authorized()
            ):
                raise SendAuthorizationRequired(
                    "Gmail send permission is required before confirmation"
                )
            plan, newly_confirmed = await self._plans.confirm(plan_id, digest)
            if not newly_confirmed:
                return self._repository.list_for_plan(plan.id)
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
                    if self._browser is None or item.validated_target is None:
                        result = ExecutionResult(
                            state=ActionState.NEEDS_USER,
                            evidence_code="browser_executor_unavailable",
                            safe_detail="The isolated browser is not available.",
                        )
                    else:
                        result = await self._browser.execute(
                            str(action.id), BrowserPayload(target=item.validated_target)
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

    def actions_for_plan(self, plan_id: str) -> tuple[ActionRecord, ...]:
        return self._repository.list_for_plan(plan_id)

    async def review_and_retry(self, action_id: str) -> ActionRecord:
        async with self._lock:
            activity = self._repository.get_activity(action_id)
            if activity is None:
                raise KeyError(action_id)
            action = activity.action
            rfc_retry = (
                action.method is UnsubscribeMethod.RFC8058
                and action.state is ActionState.FAILED
                and activity.evidence_code in {"http_429", "http_503"}
            )
            mailto_retry = (
                action.method is UnsubscribeMethod.MAILTO
                and action.state is ActionState.NEEDS_USER
                and activity.evidence_code == "gmail_send_authorization_required"
            )
            if action.retry_count >= 1 or not (rfc_retry or mailto_retry):
                raise ActionRetryNotAllowed(
                    "This action cannot be retried because its previous outcome may be "
                    "final or uncertain."
                )
            if rfc_retry and self._url_policy is None:
                raise ExecutionUnavailable("URL safety validation is unavailable")

            action = self._repository.consume_retry(action.id)
            if rfc_retry:
                action = self._repository.set_state(
                    action.id,
                    ActionState.REVIEWED,
                    evidence_code="user_reviewed_retry",
                    safe_detail="The user reviewed the eligible one-click retry.",
                )
                action = self._repository.set_state(
                    action.id,
                    ActionState.SELECTED,
                    evidence_code="user_selected_retry",
                    safe_detail="The user selected this action for one retry.",
                )
                action = self._repository.set_state(
                    action.id,
                    ActionState.CONFIRMED_BY_USER,
                    evidence_code="user_confirmed_retry",
                    safe_detail="The user explicitly confirmed one retry.",
                )
            action = self._repository.set_state(
                action.id,
                ActionState.EXECUTING,
                evidence_code="retry_started",
                safe_detail="Started the one reviewed retry.",
            )
            payload = self._cipher.decrypt(action.id, action.encrypted_payload)
            if rfc_retry:
                target = self._payload_string(payload, "target")
                assert self._url_policy is not None
                try:
                    validated_target = await self._url_policy.validate_at_plan_time(target)
                    result = await self._rfc8058.execute(Rfc8058Payload(target=validated_target))
                except UnsafeTarget:
                    result = ExecutionResult(
                        state=ActionState.FAILED,
                        evidence_code="target_revalidation_failed",
                        safe_detail="The destination failed its reviewed safety check.",
                    )
            else:
                draft = ExactMailDraft(
                    recipient=self._payload_string(payload, "recipient"),
                    subject=self._payload_string(payload, "subject"),
                    body=self._payload_string(payload, "body"),
                )
                try:
                    result = await self._mailto.execute(action_id, MailtoPayload(draft=draft))
                except SendAuthorizationRequired:
                    result = ExecutionResult(
                        state=ActionState.NEEDS_USER,
                        evidence_code="gmail_send_authorization_required",
                        safe_detail="Gmail send permission is still unavailable.",
                    )
            return self._repository.set_state(
                action.id,
                result.state,
                evidence_code=result.evidence_code,
                safe_detail=result.safe_detail,
                external_id=result.external_id,
            )

    @staticmethod
    def _payload_string(payload: dict[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str):
            raise ExecutionUnavailable("The stored action payload is invalid")
        return value

    def _build_action(self, plan: ActionPlan, item: PlannedAction) -> ActionRecord:
        semantic_fingerprint = hashlib.sha256(
            json.dumps(digest_item(item), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        action_id = uuid5(NAMESPACE_URL, f"unsubscribe-action:{semantic_fingerprint}")
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
        return ActionRecord(
            id=action_id,
            plan_id=UUID(plan.id),
            candidate_id=UUID(item.candidate_id),
            idempotency_key=semantic_fingerprint,
            method=item.method,
            state=ActionState.CONFIRMED_BY_USER,
            encrypted_payload=self._cipher.encrypt(action_id, payload),
            display_sender=item.sender,
            display_subject=item.subject,
            target_display=item.target_display,
        )
