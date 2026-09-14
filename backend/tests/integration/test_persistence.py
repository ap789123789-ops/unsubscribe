from uuid import uuid4

from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from alembic import command
from app.domain.models import ActionRecord, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.persistence.database import create_session_factory, initialize_database
from app.persistence.repositories import ActionRepository


def test_action_round_trip_keeps_the_idempotency_boundary() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    initialize_database(engine)
    repository = ActionRepository(create_session_factory(engine))
    action = ActionRecord(
        id=uuid4(),
        plan_id=uuid4(),
        candidate_id=uuid4(),
        idempotency_key="plan-42:candidate-7:rfc8058",
        method=UnsubscribeMethod.RFC8058,
        state=ActionState.CONFIRMED_BY_USER,
        encrypted_payload=b"ciphertext",
    )

    repository.add(action)

    assert repository.get(action.id) == action


def test_initial_migration_creates_privacy_safe_schema(tmp_path) -> None:
    database_path = tmp_path / "migration.sqlite3"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    schema = inspect(create_engine(f"sqlite:///{database_path}"))
    assert {
        "accounts",
        "scan_jobs",
        "messages",
        "classifications",
        "subscription_candidates",
        "candidate_messages",
        "action_plans",
        "unsubscribe_actions",
        "action_events",
    }.issubset(set(schema.get_table_names()))
    assert "body" not in {column["name"] for column in schema.get_columns("messages")}
