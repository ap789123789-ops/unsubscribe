from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.models import ActionRecord, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.executors.browser import BrowserSessionSnapshot
from app.main import create_app
from tests.api.test_candidates import local_client


class FakeBrowserSessions:
    def __init__(self) -> None:
        self.snapshot = BrowserSessionSnapshot(
            id="browser-1",
            action_id=str(uuid4()),
            state=ActionState.NEEDS_USER,
            blocker_code="login_required",
            blocker_detail="Sign-in needs your help.",
            origin="https://example.com",
            navigation_count=1,
            blocked_request_count=2,
            final_click_issued=False,
            manual_takeover=False,
        )

    def get(self, session_id: str) -> BrowserSessionSnapshot:
        assert session_id == "browser-1"
        return self.snapshot

    async def take_over(self, session_id: str) -> BrowserSessionSnapshot:
        assert session_id == "browser-1"
        return BrowserSessionSnapshot(**{**self.snapshot.__dict__, "manual_takeover": True})

    async def resume(self, session_id: str) -> ActionRecord:
        return self._action(ActionState.CONFIRMED)

    async def cancel(self, session_id: str) -> ActionRecord:
        return self._action(ActionState.REVIEWED)

    def _action(self, state: ActionState) -> ActionRecord:
        return ActionRecord(
            id=UUID(self.snapshot.action_id),
            plan_id=uuid4(),
            candidate_id=uuid4(),
            idempotency_key="browser-test",
            method=UnsubscribeMethod.BROWSER,
            state=state,
            encrypted_payload=b"ciphertext",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )


def test_browser_intervention_routes_are_safe_and_csrf_protected() -> None:
    app = create_app(browser_session_service=FakeBrowserSessions())  # type: ignore[arg-type]
    client, headers = local_client(app)

    snapshot = client.get("/api/browser-sessions/browser-1")
    assert snapshot.status_code == 200
    assert snapshot.json()["origin"] == "https://example.com"
    assert "query" not in str(snapshot.json())
    assert client.post("/api/browser-sessions/browser-1/take-over").status_code == 403

    takeover = client.post(
        "/api/browser-sessions/browser-1/take-over",
        headers=headers,
    )
    assert takeover.json()["manual_takeover"] is True
    resumed = client.post(
        "/api/browser-sessions/browser-1/resume",
        headers=headers,
    )
    assert resumed.json()["state"] == "confirmed"
    stopped = client.post(
        "/api/browser-sessions/browser-1/cancel",
        headers=headers,
    )
    assert stopped.json()["state"] == "reviewed"
