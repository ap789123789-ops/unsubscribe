from app.domain.models import ClassificationCategory
from app.main import create_app
from tests.api.test_candidates import catalog_with_candidate, local_client


def test_plan_is_immutable_redacted_and_rejects_stale_candidate() -> None:
    catalog = catalog_with_candidate()
    client, headers = local_client(create_app(candidate_catalog=catalog))
    candidate = client.get("/api/candidates").json()["items"][0]

    plan = client.post(
        "/api/action-plans",
        headers=headers,
        json={"selections": [{"candidate_id": candidate["id"], "revision": 1}]},
    )

    assert plan.status_code == 201
    assert len(plan.json()["digest"]) == 64
    assert plan.json()["items"][0]["target_display"] == "example.com"
    assert "private" not in str(plan.json())

    catalog.correct(candidate["id"], 1, ClassificationCategory.UNCLEAR)
    stale = client.post(
        "/api/action-plans",
        headers=headers,
        json={"selections": [{"candidate_id": candidate["id"], "revision": 1}]},
    )
    assert stale.status_code == 409
