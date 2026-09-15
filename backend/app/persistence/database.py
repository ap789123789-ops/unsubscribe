from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.persistence.models import Base

LEGACY_CORE_TABLES = {
    "accounts",
    "scan_jobs",
    "messages",
    "classifications",
    "subscription_candidates",
    "candidate_messages",
    "action_plans",
    "unsubscribe_actions",
    "action_events",
}
ACTIVITY_ACTION_COLUMNS = {"display_sender", "display_subject", "target_display"}


class UnrecognizedLegacySchema(RuntimeError):
    pass


def create_database_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def run_migrations(database_url: str) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        checkpoint_columns = (
            {column["name"] for column in inspector.get_columns("scan_checkpoints")}
            if "scan_checkpoints" in tables
            else set()
        )
        event_columns = (
            {column["name"] for column in inspector.get_columns("action_events")}
            if "action_events" in tables
            else set()
        )
        action_columns = (
            {column["name"] for column in inspector.get_columns("unsubscribe_actions")}
            if "unsubscribe_actions" in tables
            else set()
        )
    finally:
        engine.dispose()
    if tables and "alembic_version" not in tables:
        if not LEGACY_CORE_TABLES.issubset(tables):
            raise UnrecognizedLegacySchema(
                "The unversioned database does not match a supported legacy schema"
            )
        if "scan_checkpoints" not in tables:
            legacy_revision = "20260914_0001"
        elif not {"days", "max_messages"}.intersection(checkpoint_columns):
            legacy_revision = "20260914_0002"
        elif {"days", "max_messages"}.issubset(checkpoint_columns) and (
            "stream_sequence" in event_columns
        ):
            activity_columns = ACTIVITY_ACTION_COLUMNS.intersection(action_columns)
            if activity_columns == ACTIVITY_ACTION_COLUMNS:
                legacy_revision = "20260914_0004"
            elif not activity_columns:
                legacy_revision = "20260914_0003"
            else:
                raise UnrecognizedLegacySchema(
                    "The unversioned database has partial activity metadata"
                )
        else:
            raise UnrecognizedLegacySchema(
                "The unversioned database has an unsupported partial migration shape"
            )
        command.stamp(config, legacy_revision)
    command.upgrade(config, "head")


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
