from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.models import ActionRecord, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.main import create_app
from app.persistence.database import create_database_engine, create_session_factory, run_migrations
from app.persistence.models import ActionPlanORM, SubscriptionCandidateORM
from app.persistence.repositories import ActionRepository


def test_health_contract(tmp_path) -> None:
    application = create_app(
        settings=Settings(
            _env_file=None,
            database_url=f"sqlite:///{tmp_path / 'health.sqlite3'}",
            google_client_secrets_file=None,
            browser_profile_root=tmp_path / "health-browser-profiles",
        )
    )
    with TestClient(application) as client:
        response = client.get(
            "/api/health",
            headers={"Host": "127.0.0.1:8000"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "api_version": "v1"}


def test_database_recovery_runs_without_google_configuration(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'no-google-recovery.sqlite3'}"
    run_migrations(database_url)
    sessions = create_session_factory(create_database_engine(database_url))
    repository = ActionRepository(sessions)
    plan_id = uuid4()
    candidate_id = uuid4()
    with sessions.begin() as session:
        session.add(
            ActionPlanORM(
                id=str(plan_id),
                digest="b" * 64,
                status="confirmed",
                confirmed_at=datetime.now(UTC),
            )
        )
        session.add(
            SubscriptionCandidateORM(
                id=str(candidate_id),
                revision=1,
                grouping_key="health-recovery",
                category="reviewed",
                method="rfc8058",
                sanitized_target="example.com",
            )
        )
    action = ActionRecord(
        id=uuid4(),
        plan_id=plan_id,
        candidate_id=candidate_id,
        idempotency_key="health-recovery-action",
        method=UnsubscribeMethod.RFC8058,
        state=ActionState.EXECUTING,
        encrypted_payload=b"ciphertext",
    )
    repository.add(action)
    application = create_app(
        settings=Settings(
            _env_file=None,
            database_url=database_url,
            google_client_secrets_file=None,
            browser_profile_root=tmp_path / "recovery-browser-profiles",
        )
    )

    with TestClient(application) as client:
        assert client.get("/api/health").status_code == 200

    assert repository.get(action.id).state is ActionState.NEEDS_USER


def test_migration_and_recovery_finish_before_health_reports_ready() -> None:
    order: list[str] = []

    class RecordingRecovery:
        async def run(self) -> None:
            order.append("recovery")

    application = create_app(
        startup_migrator=lambda: order.append("migration"),
        recovery_service=RecordingRecovery(),  # type: ignore[arg-type]
    )
    assert application.state.ready is False

    with TestClient(application) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert order == ["migration", "recovery"]
