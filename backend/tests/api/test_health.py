from fastapi.testclient import TestClient

from app.main import app


def test_health_contract() -> None:
    response = TestClient(app).get(
        "/api/health",
        headers={"Host": "127.0.0.1:8000"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "api_version": "v1"}
