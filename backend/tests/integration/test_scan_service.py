import asyncio

import pytest

from app.gmail.fake import FakeGmailGateway
from app.gmail.protocols import GmailMessage, GmailMessageRef, GmailPage
from app.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from app.scan.checkpoints import SqliteScanCheckpointStore
from app.scan.service import InMemoryScanCheckpointStore, ScanFailure, ScanRequest, ScanService


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


async def test_new_service_rehydrates_checkpointed_messages_before_returning(tmp_path) -> None:
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
    assert received == ["m1", "m1"]


async def test_run_reports_gmail_failure_while_rehydrating_and_allows_retry() -> None:
    gateway = FakeGmailGateway(
        pages={},
        messages={
            "available": GmailMessage("available", "t1", 10, {}),
            "deleted": GmailMessage("deleted", "t2", 10, {}),
        },
        read_failures={"deleted": 3},
    )
    checkpoints = InMemoryScanCheckpointStore()
    request = ScanRequest(scan_id="rehydrate-partial")
    checkpoints.mark_seen(request.scan_id, "available")
    checkpoints.mark_seen(request.scan_id, "deleted")
    checkpoints.complete(request.scan_id)
    received: list[str] = []
    service = ScanService(gateway, checkpoints, lambda message: received.append(message.id))

    with pytest.raises(ScanFailure, match="gmail_access_unavailable") as error:
        await service.run(request)
    result = await service.run(request)

    assert error.value.code == "gmail_access_unavailable"
    assert result.completed is True
    assert received == ["available", "available", "deleted"]


async def test_run_reports_processing_failure_while_rehydrating_and_allows_retry() -> None:
    gateway = FakeGmailGateway(
        pages={},
        messages={"m1": GmailMessage("m1", "t1", 10, {})},
    )
    checkpoints = InMemoryScanCheckpointStore()
    request = ScanRequest(scan_id="rehydrate-processing")
    checkpoints.mark_seen(request.scan_id, "m1")
    checkpoints.complete(request.scan_id)
    should_fail = True
    received: list[str] = []

    def sink(message: GmailMessage) -> None:
        nonlocal should_fail
        if should_fail:
            should_fail = False
            raise ValueError("synthetic normalization failure")
        received.append(message.id)

    service = ScanService(gateway, checkpoints, sink)

    with pytest.raises(ScanFailure, match="message_processing_failed") as error:
        await service.run(request)
    result = await service.run(request)

    assert error.value.code == "message_processing_failed"
    assert result.completed is True
    assert received == ["m1"]


async def test_concurrent_runs_for_one_scan_are_serialized() -> None:
    gateway = FakeGmailGateway(
        pages={None: GmailPage((GmailMessageRef("m1", "t1"),), None)},
        messages={"m1": GmailMessage("m1", "t1", 10, {})},
    )
    checkpoints = InMemoryScanCheckpointStore()
    request = ScanRequest(scan_id="concurrent-scan")
    sink_started = asyncio.Event()
    release_sink = asyncio.Event()
    received: list[str] = []

    async def slow_sink(message: GmailMessage) -> None:
        received.append(message.id)
        sink_started.set()
        await release_sink.wait()

    service = ScanService(gateway, checkpoints, slow_sink)
    first = asyncio.create_task(service.run(request))
    await sink_started.wait()
    second = asyncio.create_task(service.run(request))
    await asyncio.sleep(0)
    release_sink.set()
    first_result, second_result = await asyncio.gather(first, second)

    assert first_result.completed is True
    assert second_result.completed is True
    assert received == ["m1"]
    assert gateway.read_attempts["m1"] == 1
