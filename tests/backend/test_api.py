"""API contract smoke and behavior tests."""

from uuid import UUID

from fastapi.testclient import TestClient


def test_liveness(client: TestClient) -> None:
    response = client.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_checks_composed_modules(client: TestClient) -> None:
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "configuration": "ok",
            "registry": "ok",
            "source_registry": "ok",
            "candidate_read_model": "ok",
            "engagement_guard": "ok",
        },
    }


def test_version_declares_bounded_contexts(client: TestClient) -> None:
    response = client.get("/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "0.1.0"
    assert payload["api_version"] == "v1"
    assert payload["modules"] == [
        "platform",
        "registry",
        "identity",
        "engagement",
        "acquisition",
    ]


def test_capabilities_fail_closed_by_default(client: TestClient) -> None:
    response = client.get("/v1/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "dataset_mode": "synthetic",
        "ingestion_enabled": False,
        "alert_delivery_mode": "log",
        "outreach_mode": "disabled",
        "outreach_send_enabled": False,
        "outreach_human_approval_required": True,
        "external_effects_enabled": False,
    }


def test_candidates_are_synthetic_and_launch_counties_only(client: TestClient) -> None:
    response = client.get("/v1/candidates")

    assert response.status_code == 200
    assert response.headers["etag"] == '"synthetic-candidate-v1"'
    payload = response.json()
    assert payload["dataset_mode"] == "synthetic"
    assert payload["total"] == 3
    assert {candidate["county_name"] for candidate in payload["items"]} == {
        "Travis County",
        "Bastrop County",
        "Caldwell County",
    }
    assert all(candidate["synthetic"] for candidate in payload["items"])
    assert all(candidate["parcel_id"].startswith("TX-") for candidate in payload["items"])
    assert all(
        candidate["value_range"]["high"] >= candidate["value_range"]["low"]
        for candidate in payload["items"]
    )
    assert all(candidate["likely_basis"] > 0 for candidate in payload["items"])


def test_candidate_cursor_and_detail(client: TestClient) -> None:
    first_page = client.get("/v1/candidates", params={"limit": 1}).json()
    assert first_page["next_cursor"]

    second_response = client.get(
        "/v1/candidates",
        params={"limit": 1, "cursor": first_page["next_cursor"]},
    )
    assert second_response.status_code == 200
    second_page = second_response.json()
    assert second_page["items"][0]["rank"] == 2

    candidate_id = UUID(second_page["items"][0]["id"])
    detail = client.get(f"/v1/candidates/{candidate_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == str(candidate_id)


def test_candidate_conditional_request(client: TestClient) -> None:
    response = client.get(
        "/v1/candidates",
        headers={"If-None-Match": '"synthetic-candidate-v1"'},
    )

    assert response.status_code == 304
    assert response.content == b""


def test_invalid_cursor_uses_problem_details(client: TestClient) -> None:
    response = client.get("/v1/candidates", params={"cursor": "not-a-cursor"})

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "about:blank",
        "title": "Bad Request",
        "status": 400,
        "detail": "cursor is malformed",
        "instance": "/v1/candidates",
    }


def test_candidate_not_found_uses_problem_details(client: TestClient) -> None:
    response = client.get("/v1/candidates/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

    assert response.status_code == 404
    assert response.json()["detail"] == "Candidate not found"
