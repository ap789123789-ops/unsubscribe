import json

from sqlalchemy.orm import Session, sessionmaker

from app.persistence.models import ScanCheckpointORM, utcnow


class SqliteScanCheckpointStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _get_or_create(self, session: Session, scan_id: str) -> ScanCheckpointORM:
        row = session.get(ScanCheckpointORM, scan_id)
        if row is None:
            row = ScanCheckpointORM(scan_id=scan_id)
            session.add(row)
            session.flush()
        return row

    def page_token(self, scan_id: str) -> str | None:
        with self._session_factory() as session:
            row = session.get(ScanCheckpointORM, scan_id)
            return row.next_page_token if row else None

    def has_seen(self, scan_id: str, message_id: str) -> bool:
        with self._session_factory() as session:
            row = session.get(ScanCheckpointORM, scan_id)
            return bool(row and message_id in json.loads(row.seen_message_ids_json))

    def mark_seen(self, scan_id: str, message_id: str) -> None:
        with self._session_factory.begin() as session:
            row = self._get_or_create(session, scan_id)
            seen = set(json.loads(row.seen_message_ids_json))
            seen.add(message_id)
            row.seen_message_ids_json = json.dumps(sorted(seen))
            row.updated_at = utcnow()

    def checkpoint_page(self, scan_id: str, next_page_token: str | None) -> None:
        with self._session_factory.begin() as session:
            row = self._get_or_create(session, scan_id)
            row.next_page_token = next_page_token
            row.updated_at = utcnow()

    def count(self, scan_id: str) -> int:
        with self._session_factory() as session:
            row = session.get(ScanCheckpointORM, scan_id)
            return len(json.loads(row.seen_message_ids_json)) if row else 0

    def is_complete(self, scan_id: str) -> bool:
        with self._session_factory() as session:
            row = session.get(ScanCheckpointORM, scan_id)
            return bool(row and row.completed)

    def complete(self, scan_id: str) -> None:
        with self._session_factory.begin() as session:
            row = self._get_or_create(session, scan_id)
            row.completed = 1
            row.updated_at = utcnow()
