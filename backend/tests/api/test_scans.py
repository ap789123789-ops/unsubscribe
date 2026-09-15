from fastapi.testclient import TestClient

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
