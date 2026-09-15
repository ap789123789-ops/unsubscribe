from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.domain.models import ActionRecord, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.main import create_app
from app.persistence.database import create_session_factory, initialize_database
from app.persistence.repositories import ActionRepository
from tests.api.test_candidates import local_client


def activity_repository() -> ActionRepository:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    initialize_database(engine)
    return ActionRepository(create_session_factory(engine))


def test_global_activity_api_returns_identity_latest_evidence_and_browser_session() -> None:
    repository = activity_repository()
    action = ActionRecord(
        id=uuid4(),
        plan_id=uuid4(),
        candidate_id=uuid4(),
        idempotency_key="activity-api-browser",
        method=UnsubscribeMethod.BROWSER,
        state=ActionState.EXECUTING,
        encrypted_payload=b"ciphertext",
        display_sender="Community <hello@community.example>",
        display_subject="September update",
        target_display="community.example",
        created_at=datetime(2026, 9, 14, 12, tzinfo=UTC),
        updated_at=datetime(2026, 9, 14, 12, tzinfo=UTC),
    )
    repository.add(action)
    repository.set_state(
        action.id,
        ActionState.NEEDS_USER,
        evidence_code="login_required",
        safe_detail="Sign in to the sender's site, then resume automation.",
        external_id="browser-session-1",
    )
    client, _ = local_client(create_app(event_repository=repository))

    response = client.get("/api/actions")

    assert response.status_code == 200
    item = response.json()["items"][0]
    updated_at = item.pop("updated_at")
    assert item == {
        "id": str(action.id),
        "plan_id": str(action.plan_id),
        "candidate_id": str(action.candidate_id),
        "sender": "Community <hello@community.example>",
        "subject": "September update",
        "target_display": "community.example",
        "method": "browser",
        "state": "needs_user",
        "evidence_code": "login_required",
        "safe_detail": "Sign in to the sender's site, then resume automation.",
        "retry_available": False,
        "browser_session_id": "browser-session-1",
    }
    assert datetime.fromisoformat(updated_at).tzinfo is not None


def test_activity_retry_flag_requires_matching_method_state_and_evidence() -> None:
    repository = activity_repository()
    action = ActionRecord(
        id=uuid4(),
        plan_id=uuid4(),
        candidate_id=uuid4(),
        idempotency_key="activity-api-mismatched-retry",
        method=UnsubscribeMethod.MAILTO,
        state=ActionState.EXECUTING,
        encrypted_payload=b"ciphertext",
    )
    repository.add(action)
    repository.set_state(
        action.id,
        ActionState.FAILED,
        evidence_code="http_503",
        safe_detail="This evidence belongs only to the RFC executor.",
    )
    client, _ = local_client(create_app(event_repository=repository))

    item = client.get("/api/actions").json()["items"][0]

    assert item["retry_available"] is False
