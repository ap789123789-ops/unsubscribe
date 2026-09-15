import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.models import ActionRecord, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.main import create_app
from app.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from app.persistence.models import ActionEventORM, ActionPlanORM, SubscriptionCandidateORM
from app.persistence.repositories import ActionRepository


def action_with_events(tmp_path) -> tuple[ActionRepository, ActionRecord]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'events.sqlite3'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    repository = ActionRepository(sessions)
    plan_id = uuid4()
    candidate_id = uuid4()
    with sessions.begin() as session:
        session.add(
            ActionPlanORM(
                id=str(plan_id),
                digest=uuid4().hex + uuid4().hex,
                status="confirmed",
                confirmed_at=datetime.now(UTC),
            )
        )
        session.add(
            SubscriptionCandidateORM(
                id=str(candidate_id),
                revision=1,
                grouping_key=f"events:{candidate_id}",
                category="reviewed",
                method=UnsubscribeMethod.RFC8058.value,
                sanitized_target="example.com",
            )
        )
    action = ActionRecord(
        id=uuid4(),
        plan_id=plan_id,
        candidate_id=candidate_id,
        idempotency_key=f"events:{uuid4()}",
        method=UnsubscribeMethod.RFC8058,
        state=ActionState.CONFIRMED_BY_USER,
        encrypted_payload=b"ciphertext",
    )
    repository.add(action)
    repository.set_state(
        action.id,
        ActionState.EXECUTING,
        evidence_code="execution_started",
        safe_detail="Execution started.",
    )
    final = repository.set_state(
        action.id,
        ActionState.SUBMITTED,
        evidence_code="request_submitted",
        safe_detail="The request was submitted.",
    )
    with sessions.begin() as session:
        submitted_event = (
            session.query(ActionEventORM)
            .filter_by(
                action_id=str(action.id),
                to_state=ActionState.SUBMITTED.value,
            )
            .one()
        )
        submitted_event.created_at = datetime(2000, 1, 1, tzinfo=UTC)
    return repository, final


def event_blocks(body: str) -> list[dict[str, object]]:
    blocks = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        blocks.append({"id": fields["id"], "data": json.loads(fields["data"])})
    return blocks


def test_action_event_stream_replays_only_events_after_last_event_id(tmp_path) -> None:
    repository, action = action_with_events(tmp_path)
    client = TestClient(
        create_app(event_repository=repository),
        base_url="http://127.0.0.1:8000",
    )

    initial = client.get(f"/events/actions/{action.plan_id}")
    initial_events = event_blocks(initial.text)
    replay = client.get(
        f"/events/actions/{action.plan_id}",
        headers={"Last-Event-ID": str(initial_events[0]["id"])},
    )
    replay_events = event_blocks(replay.text)

    assert initial.status_code == 200
    assert initial.headers["content-type"].startswith("text/event-stream")
    assert initial.headers["cache-control"] == "no-cache, no-store"
    assert [event["data"]["state"] for event in initial_events] == [
        "executing",
        "submitted",
    ]
    assert len(replay_events) == 1
    assert replay_events[0]["id"] == initial_events[1]["id"]
    assert replay_events[0]["data"] == {
        "action_id": str(action.id),
        "state": "submitted",
        "evidence_code": "request_submitted",
        "safe_detail": "The request was submitted.",
    }


def test_action_event_stream_is_documented_as_sse(tmp_path) -> None:
    repository, _ = action_with_events(tmp_path)
    app = create_app(event_repository=repository)

    content = app.openapi()["paths"]["/events/actions/{plan_id}"]["get"]["responses"]["200"][
        "content"
    ]

    assert "text/event-stream" in content
    assert "application/json" not in content
