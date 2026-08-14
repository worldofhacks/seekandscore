"""API contract smoke and fail-closed live-runtime behavior tests."""

from fastapi.testclient import TestClient


def test_liveness(client: TestClient) -> None:
    response = client.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_checks_composed_modules(client: TestClient) -> None:
    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "configuration": "ok",
            "registry": "ok",
            "source_registry": "ok",
            "candidate_read_model": "failed",
            "research_store": "ok",
            "engagement_guard": "ok",
        },
    }


def test_version_declares_bounded_contexts(client: TestClient) -> None:
    response = client.get("/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "0.1.0"
    assert payload["api_version"] == "v1"
    assert payload["read_model_version"] == "live-assessor-oz-evidence-v3"
    assert payload["dataset_mode"] == "live"
    assert payload["candidate_serving_mode"] == "unavailable"
    assert "synthetic" not in response.text.lower()
    assert payload["modules"] == [
        "platform",
        "registry",
        "identity",
        "geography",
        "engagement",
        "deal",
        "acquisition",
    ]


def test_capabilities_fail_closed_by_default(client: TestClient) -> None:
    response = client.get("/v1/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "dataset_mode": "live",
        "candidate_serving_mode": "unavailable",
        "candidate_read_model_ready": False,
        "live_candidate_display_enabled": False,
        "oz_2018_private_display_enabled": False,
        "ingestion_enabled": False,
        "research_writes_enabled": False,
        "research_store_ready": False,
        "alert_delivery_mode": "log",
        "outreach_mode": "disabled",
        "outreach_send_enabled": False,
        "outreach_human_approval_required": True,
        "external_effects_enabled": False,
    }


def test_candidates_return_honest_live_error_without_database(client: TestClient) -> None:
    response = client.get("/v1/candidates")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert "etag" not in response.headers
    payload = response.json()
    assert payload["dataset_mode"] == "live"
    assert payload["dataset_status"] == "error"
    assert payload["items"] == []
    assert payload["total"] == 0
    assert payload["sources"][0]["status"] == "unavailable"
    assert "not configured" in payload["warnings"][0]
    assert "synthetic" not in response.text.lower()


def test_candidate_conditional_request(client: TestClient) -> None:
    response = client.get(
        "/v1/candidates",
        headers={"If-None-Match": '"live-assessor-explorer-v2:stale-cache"'},
    )

    assert response.status_code == 503
    assert response.json()["dataset_status"] == "error"


def test_candidate_detail_reports_store_unavailable(client: TestClient) -> None:
    response = client.get("/v1/candidates/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

    assert response.status_code == 503
    assert response.json()["detail"] == "The live candidate store is not configured."
