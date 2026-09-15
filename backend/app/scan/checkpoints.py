import json

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.models import ScanCheckpointORM, utcnow
from app.scan.service import ScanRequest


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

    def remember_request(self, request: ScanRequest) -> None:
        with self._session_factory.begin() as session:
            row = self._get_or_create(session, request.scan_id)
            row.days = request.days
            row.max_messages = request.max_messages
            row.updated_at = utcnow()

    def incomplete_requests(self) -> tuple[ScanRequest, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ScanCheckpointORM)
                .where(ScanCheckpointORM.completed == 0)
                .order_by(ScanCheckpointORM.updated_at, ScanCheckpointORM.scan_id)
            )
            return tuple(
                ScanRequest(
                    scan_id=row.scan_id,
                    days=row.days,
                    max_messages=row.max_messages,
                )
                for row in rows
            )

    def seen_message_ids(self, scan_id: str) -> tuple[str, ...]:
        with self._session_factory() as session:
            row = session.get(ScanCheckpointORM, scan_id)
            if row is None:
                return ()
            return tuple(json.loads(row.seen_message_ids_json))

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
