from fastapi.testclient import TestClient

from app.config import Settings
from app.gmail.fake import FakeGmailGateway
from app.gmail.protocols import GmailMessage, GmailMessageRef, GmailPage
from app.main import create_app
from app.scan.service import InMemoryScanCheckpointStore, ScanService


def test_scan_api_enforces_bounds_and_returns_completed_result() -> None:
    gateway = FakeGmailGateway(
        pages={
            None: GmailPage((GmailMessageRef("m1", "t1"),), None),
        },
        messages={"m1": GmailMessage("m1", "t1", 10, {})},
    )
    service = ScanService(gateway, InMemoryScanCheckpointStore(), lambda _: None)
    client = TestClient(
        create_app(scan_service=service),
        base_url="http://127.0.0.1:8000",
    )
    csrf = client.get("/api/session").json()["csrf_token"]
    headers = {"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": csrf}

    response = client.post(
        "/api/scans",
        headers=headers,
        json={"scan_id": "scan-api", "days": 30, "max_messages": 500},
    )

    assert response.status_code == 200
    assert response.json() == {
        "scan_id": "scan-api",
        "processed_count": 1,
        "completed": True,
    }
    assert (
        client.post(
            "/api/scans",
            headers=headers,
            json={"days": 30, "max_messages": 501},
        ).status_code
        == 422
    )


def test_scan_api_distinguishes_message_processing_failure_from_gmail_access() -> None:
    gateway = FakeGmailGateway(
        pages={None: GmailPage((GmailMessageRef("m1", "t1"),), None)},
        messages={"m1": GmailMessage("m1", "t1", 10, {})},
    )

    def fail_processing(_: GmailMessage) -> None:
        raise AttributeError("provider-controlled detail must not reach the response")

    service = ScanService(
        gateway,
        InMemoryScanCheckpointStore(),
        fail_processing,
        retry_delays=(0,),
    )
    client = TestClient(
        create_app(scan_service=service),
        base_url="http://127.0.0.1:8000",
        raise_server_exceptions=False,
    )
    csrf = client.get("/api/session").json()["csrf_token"]

    response = client.post(
        "/api/scans",
        headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": csrf},
        json={"scan_id": "processing-failure", "days": 30, "max_messages": 1},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "message_processing_failed",
            "message": "One email could not be processed. Progress was saved; retry the scan.",
            "scan_id": "processing-failure",
        }
    }
    assert "provider-controlled" not in response.text


def test_scan_failure_is_written_to_a_sanitized_local_log(tmp_path) -> None:
    gateway = FakeGmailGateway(
        pages={None: GmailPage((GmailMessageRef("m1", "t1"),), None)},
        messages={"m1": GmailMessage("m1", "t1", 10, {})},
    )

    def fail_processing(_: GmailMessage) -> None:
        raise AttributeError("private email content")

    log_file = tmp_path / "logs" / "unsubscribe.log"
    service = ScanService(
        gateway,
        InMemoryScanCheckpointStore(),
        fail_processing,
        retry_delays=(0,),
    )
    client = TestClient(
        create_app(
            settings=Settings(
                _env_file=None,
                database_url=f"sqlite:///{tmp_path / 'scan.db'}",
                log_file=log_file,
            ),
            scan_service=service,
        ),
        base_url="http://127.0.0.1:8000",
        raise_server_exceptions=False,
    )
    csrf = client.get("/api/session").json()["csrf_token"]

    response = client.post(
        "/api/scans",
        headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": csrf},
        json={"scan_id": "logged-processing-failure", "days": 30, "max_messages": 1},
    )

    assert response.status_code == 500
    log = log_file.read_text()
    assert "scan_id='logged-processing-failure'" in log
    assert "code=message_processing_failed" in log
    assert "cause=AttributeError" in log
    assert "test_scans.py" in log
    assert "private email content" not in log
