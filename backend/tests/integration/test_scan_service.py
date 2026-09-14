from app.gmail.fake import FakeGmailGateway
from app.gmail.protocols import GmailMessage, GmailMessageRef, GmailPage
from app.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from app.scan.checkpoints import SqliteScanCheckpointStore
from app.scan.service import InMemoryScanCheckpointStore, ScanRequest, ScanService


async def test_scan_retries_reads_checkpoints_pages_and_deduplicates_resume() -> None:
    gateway = FakeGmailGateway(
        pages={
            None: GmailPage(
                messages=(
                    GmailMessageRef(id="a", thread_id="ta"),
                    GmailMessageRef(id="b", thread_id="tb"),
                ),
                next_page_token="page-2",
            ),
            "page-2": GmailPage(
                messages=(
                    GmailMessageRef(id="b", thread_id="tb"),
                    GmailMessageRef(id="c", thread_id="tc"),
                ),
                next_page_token=None,
            ),
        },
        messages={
            key: GmailMessage(id=key, thread_id=f"t{key}", size_estimate=100, payload={})
            for key in ("a", "b", "c")
        },
        read_failures={"a": 2},
    )
    checkpoints = InMemoryScanCheckpointStore()
    received: list[str] = []
    service = ScanService(gateway, checkpoints, lambda message: received.append(message.id))
    request = ScanRequest(scan_id="scan-1", days=30, max_messages=500)

    result = await service.run(request)
    resumed = await service.run(request)

    assert result.processed_count == 3
    assert resumed.processed_count == 3
    assert received == ["a", "b", "c"]
    assert gateway.read_attempts["a"] == 3
    assert checkpoints.page_tokens == ["page-2", None]


async def test_sqlite_checkpoint_survives_a_new_service_instance(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'scan.sqlite3'}")
    initialize_database(engine)
    factory = create_session_factory(engine)
    gateway = FakeGmailGateway(
        pages={None: GmailPage((GmailMessageRef("m1", "t1"),), None)},
        messages={"m1": GmailMessage("m1", "t1", 10, {})},
    )
    received: list[str] = []
    request = ScanRequest(scan_id="durable-scan")

    await ScanService(
        gateway,
        SqliteScanCheckpointStore(factory),
        lambda message: received.append(message.id),
    ).run(request)
    result = await ScanService(
        gateway,
        SqliteScanCheckpointStore(factory),
        lambda message: received.append(message.id),
    ).run(request)

    assert result.completed is True
    assert result.processed_count == 1
    assert received == ["m1"]
