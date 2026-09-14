from fastapi.testclient import TestClient

from app.main import create_app


def test_local_session_protects_mutations() -> None:
    client = TestClient(create_app(), base_url="http://127.0.0.1:8000")
    session = client.get("/api/session")
    csrf_token = session.json()["csrf_token"]

    assert session.status_code == 200
    assert "HttpOnly" in session.headers["set-cookie"]
    assert "SameSite=strict" in session.headers["set-cookie"]
    assert client.post("/api/session/verify").status_code == 403
    assert (
        client.post(
            "/api/session/verify",
            headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": "wrong"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/session/verify",
            headers={
                "Origin": "http://127.0.0.1:8000",
                "X-CSRF-Token": csrf_token,
            },
        ).json()
        == {"verified": True}
    )


def test_unexpected_host_is_rejected() -> None:
    client = TestClient(create_app())

    assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 400

