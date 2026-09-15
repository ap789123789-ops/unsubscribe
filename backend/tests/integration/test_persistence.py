from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from alembic import command
from app.domain.models import ActionRecord, UnsubscribeMethod
from app.domain.state_machine import ActionState
from app.persistence.database import (
    create_session_factory,
    initialize_database,
    run_migrations,
)
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


def test_activity_projection_is_newest_first_and_keeps_latest_safe_evidence() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    initialize_database(engine)
    repository = ActionRepository(create_session_factory(engine))
    older_plan_id = uuid4()
    newer_plan_id = uuid4()
    started_at = datetime(2026, 9, 14, 12, tzinfo=UTC)
    older = ActionRecord(
        id=uuid4(),
        plan_id=older_plan_id,
        candidate_id=uuid4(),
        idempotency_key="activity-older",
        method=UnsubscribeMethod.RFC8058,
        state=ActionState.EXECUTING,
        encrypted_payload=b"ciphertext",
        display_sender="Morning Brief <brief@example.com>",
        display_subject="Monday edition",
        target_display="example.com",
        created_at=started_at,
        updated_at=started_at,
    )
    newer = ActionRecord(
        id=uuid4(),
        plan_id=newer_plan_id,
        candidate_id=uuid4(),
        idempotency_key="activity-newer",
        method=UnsubscribeMethod.BROWSER,
        state=ActionState.EXECUTING,
        encrypted_payload=b"ciphertext",
        display_sender="Community <hello@community.example>",
        display_subject="September update",
        target_display="community.example",
        created_at=started_at + timedelta(minutes=1),
        updated_at=started_at + timedelta(minutes=1),
    )
    repository.add(older)
    repository.add(newer)
    repository.set_state(
        older.id,
        ActionState.SUBMITTED,
        evidence_code="rfc8058_request_accepted",
        safe_detail="The request was accepted; list processing is not verified.",
    )
    repository.set_state(
        newer.id,
        ActionState.NEEDS_USER,
        evidence_code="login_required",
        safe_detail="Sign in to continue.",
        external_id="browser-session-1",
    )

    activity = repository.list_activity()
    filtered = repository.list_activity(plan_id=str(older_plan_id))

    assert [item.action.id for item in activity] == [newer.id, older.id]
    assert activity[0].action.display_sender == "Community <hello@community.example>"
    assert activity[0].action.display_subject == "September update"
    assert activity[0].action.target_display == "community.example"
    assert activity[0].evidence_code == "login_required"
    assert activity[0].safe_detail == "Sign in to continue."
    assert [item.action.id for item in filtered] == [older.id]


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
        "scan_checkpoints",
    }.issubset(set(schema.get_table_names()))
    assert "body" not in {column["name"] for column in schema.get_columns("messages")}
    assert {"days", "max_messages"}.issubset(
        {column["name"] for column in schema.get_columns("scan_checkpoints")}
    )
    assert len(schema.get_unique_constraints("action_plans")) == 1
    assert schema.get_pk_constraint("action_events")["constrained_columns"] == ["stream_sequence"]
    assert {"display_sender", "display_subject", "target_display"}.issubset(
        {column["name"] for column in schema.get_columns("unsubscribe_actions")}
    )


def test_startup_migrates_an_existing_pre_alembic_database(tmp_path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    database_url = f"sqlite:///{database_path}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20260914_0002")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO action_plans
                (id, digest, status, confirmed_at, created_at)
                VALUES ('plan-before-upgrade', :digest, 'confirmed', NULL, CURRENT_TIMESTAMP)"""
            ),
            {"digest": "a" * 64},
        )
        connection.execute(
            text(
                """INSERT INTO subscription_candidates
                (id, revision, grouping_key, category, method, sanitized_target)
                VALUES ('candidate-before-upgrade', 1, 'legacy:key', 'reviewed',
                        'rfc8058', 'example.com')"""
            )
        )
        connection.execute(
            text(
                """INSERT INTO unsubscribe_actions
                (id, plan_id, candidate_id, idempotency_key, method, state,
                 encrypted_payload, retry_count, outbound_message_id, external_id,
                 created_at, updated_at)
                VALUES ('action-before-upgrade', 'plan-before-upgrade',
                        'candidate-before-upgrade', 'legacy-idempotency', 'rfc8058',
                        'submitted', :payload, 0, NULL, 'receipt-before-upgrade',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""
            ),
            {"payload": b"encrypted-before-upgrade"},
        )
        connection.execute(
            text(
                """INSERT INTO action_events
                (id, action_id, sequence, from_state, to_state, evidence_code,
                 safe_detail, created_at)
                VALUES ('event-before-upgrade', 'action-before-upgrade', 1,
                        'executing', 'submitted', 'legacy-receipt',
                        'Submission was recorded.', CURRENT_TIMESTAMP)"""
            )
        )
        connection.execute(text("DROP TABLE alembic_version"))
    engine.dispose()

    run_migrations(database_url)

    schema = inspect(create_engine(database_url))
    assert "alembic_version" in schema.get_table_names()
    assert {"days", "max_messages"}.issubset(
        {column["name"] for column in schema.get_columns("scan_checkpoints")}
    )
    assert len(schema.get_unique_constraints("action_plans")) == 1
    assert any(
        key["referred_table"] == "action_plans"
        for key in schema.get_foreign_keys("unsubscribe_actions")
    )
    with create_engine(database_url).connect() as connection:
        assert (
            connection.scalar(
                text("SELECT external_id FROM unsubscribe_actions WHERE id='action-before-upgrade'")
            )
            == "receipt-before-upgrade"
        )
        assert (
            connection.scalar(
                text("SELECT evidence_code FROM action_events WHERE id='event-before-upgrade'")
            )
            == "legacy-receipt"
        )
        assert (
            connection.scalar(
                text(
                    "SELECT display_sender FROM unsubscribe_actions "
                    "WHERE id='action-before-upgrade'"
                )
            )
            == "Unknown sender"
        )


def test_startup_recognizes_a_pre_checkpoint_unversioned_database(tmp_path) -> None:
    database_path = tmp_path / "pre-checkpoint.sqlite3"
    database_url = f"sqlite:///{database_path}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20260914_0001")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
    engine.dispose()

    run_migrations(database_url)

    schema = inspect(create_engine(database_url))
    assert {"days", "max_messages"}.issubset(
        {column["name"] for column in schema.get_columns("scan_checkpoints")}
    )
    assert schema.get_pk_constraint("action_events")["constrained_columns"] == ["stream_sequence"]
