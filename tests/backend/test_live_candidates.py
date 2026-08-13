"""DB-independent live candidate and API provenance contract tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID

from fastapi.testclient import TestClient

from seekandscore.acquisition.models import (
    NormalizedParcelObservation,
    RawArtifact,
    SourceRun,
    SourceRunStatus,
)
from seekandscore.acquisition.repository import (
    MemoryAcquisitionRepository,
    PostgresAcquisitionRepository,
)
from seekandscore.api import create_app
from seekandscore.api.dependencies import get_container
from seekandscore.bootstrap import AppContainer
from seekandscore.platform.settings import Settings
from seekandscore.readmodels import LiveCandidateRepository
from seekandscore.registry import InMemorySourceRegistry

NOW = datetime(2026, 8, 13, 12, tzinfo=UTC)
SHA = "a" * 64


def seeded_repository() -> MemoryAcquisitionRepository:
    repository = MemoryAcquisitionRepository()
    artifact = RawArtifact(
        id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        source_id="travis_tcad_parcels",
        sha256=SHA,
        byte_count=100,
        media_type="application/json",
        storage_uri="s3://private/artifact.json",
        original_uri="https://example.invalid/query",
        request_params={},
        response_etag='"etag"',
        retrieved_at=NOW,
    )
    repository.save_artifact(artifact)
    observation = NormalizedParcelObservation(
        id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        source_id="travis_tcad_parcels",
        source_record_id="101",
        artifact_id=artifact.id,
        artifact_sha256=SHA,
        parser_version="travis-tcad-parcel-v1",
        jurisdiction_id="us-tx-travis",
        local_parcel_id="700001",
        geographic_id="GEO-001",
        situs_address="100 TEST RD DEL VALLE 78617",
        situs_city="DEL VALLE",
        situs_zip="78617",
        tcad_acres=2.5,
        gis_acres=2.48,
        market_value_cents=50_000_000,
        appraised_value_cents=48_000_000,
        assessed_value_cents=45_000_000,
        improvement_value_cents=15_000_000,
        land_value_cents=35_000_000,
        first_improvement_year=2001,
        observed_at=NOW,
    )
    repository.save_observations((observation,))
    repository.save_run(
        SourceRun(
            id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
            source_id="travis_tcad_parcels",
            status=SourceRunStatus.SUCCEEDED,
            requested_at=NOW,
            started_at=NOW,
            completed_at=NOW,
            records_fetched=1,
            observations_created=1,
            artifact_ids=(artifact.id,),
            adapter_version="travis-tcad-arcgis-v1",
            parser_version="travis-tcad-parcel-v1",
            configuration_hash="d" * 64,
            activation_id="private-activation-id",
        )
    )
    return repository


def test_postgres_insert_count_uses_returned_ids_not_indeterminate_rowcount() -> None:
    engine = MagicMock()
    result = engine.begin.return_value.__enter__.return_value.execute.return_value
    result.rowcount = -1
    result.scalars.return_value = (
        UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
    )
    source = seeded_repository()
    observation = next(iter(source.observations.values()))
    second = observation.model_copy(update={"id": UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")})

    inserted = PostgresAcquisitionRepository(engine).save_observations((observation, second))

    assert inserted == 2


def test_live_projection_labels_assessor_values_and_oz_as_unverified() -> None:
    repository = LiveCandidateRepository(
        seeded_repository(),
        InMemorySourceRegistry(),
        display_enabled=True,
    )

    page = repository.list(limit=25, cursor=None, dataset_mode="live")

    assert page.dataset_status == "current"
    assert page.partial is False
    assert page.retrieved_at == NOW
    assert page.published_at is None
    assert page.sources[0].status == "current"
    candidate = page.items[0]
    assert candidate.synthetic is False
    assert candidate.screening_only is True
    assert candidate.strategy == "assessor"
    assert candidate.opportunity_zone_status == "review"
    assert candidate.likely_basis == 0
    assert "no investment" in candidate.thesis
    assert candidate.source_observation is not None
    assert candidate.source_observation.fields.appraised_value_cents == 48_000_000
    assert candidate.source_observation.fields.assessed_value_cents == 45_000_000


def test_live_projection_fails_closed_when_display_rights_are_not_approved() -> None:
    repository = LiveCandidateRepository(
        seeded_repository(),
        InMemorySourceRegistry(),
        display_enabled=False,
    )

    page = repository.list(limit=25, cursor=None, dataset_mode="live")

    assert page.items == ()
    assert page.dataset_status == "fallback"
    assert "rights review" in page.warnings[0]


def test_container_requires_registry_display_permission_even_with_environment_approval() -> None:
    settings = Settings(
        app_env="test",
        dataset_mode="live",
        database_url="sqlite://",
        live_source_display_enabled=True,
        live_source_display_approval_id="environment-approval-only",
    )
    container = AppContainer.build(settings)

    page = container.candidates.list(limit=25, cursor=None, dataset_mode="live")

    assert page.items == ()
    assert page.dataset_status == "fallback"
    assert "public display is disabled" in page.warnings[0]


def test_freshness_marks_monthly_source_stale() -> None:
    acquisition = seeded_repository()
    source_registry = InMemorySourceRegistry()
    last_run = acquisition.latest_run("travis_tcad_parcels")
    assert last_run is not None

    freshness = source_registry.freshness(
        "travis_tcad_parcels",
        last_run,
        now=NOW + timedelta(days=46),
    )

    assert freshness.status == "stale"
    assert freshness.stale_after == NOW + timedelta(days=45)


def test_source_api_exposes_sanitized_run_summary_only() -> None:
    settings = Settings(app_env="test")
    app = create_app(settings)
    container = AppContainer.build(settings)
    object.__setattr__(container, "source_runs", seeded_repository())
    app.dependency_overrides[get_container] = lambda: container

    with TestClient(app) as client:
        response = client.get("/v1/sources/travis_tcad_parcels")

    assert response.status_code == 200
    payload_text = response.text
    assert "private-activation-id" not in payload_text
    assert SHA not in payload_text
    assert "artifact_ids" not in payload_text
    assert response.json()["latest_run"] == {
        "status": "succeeded",
        "started_at": "2026-08-13T12:00:00Z",
        "completed_at": "2026-08-13T12:00:00Z",
        "records_fetched": 1,
        "observations_created": 1,
        "records_quarantined": 0,
        "partial": False,
    }


def test_live_projection_cursor_detail_and_partial_status() -> None:
    acquisition = seeded_repository()
    current = acquisition.latest_run("travis_tcad_parcels")
    assert current is not None
    acquisition.save_run(
        current.model_copy(
            update={
                "id": UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
                "status": SourceRunStatus.PARTIAL,
                "partial": True,
                "started_at": NOW + timedelta(seconds=1),
                "completed_at": NOW + timedelta(seconds=1),
            }
        )
    )
    repository = LiveCandidateRepository(
        acquisition,
        InMemorySourceRegistry(),
        display_enabled=True,
    )

    page = repository.list(limit=1, cursor=None, dataset_mode="live")
    candidate = page.items[0]

    assert page.dataset_status == "partial"
    assert repository.get(candidate.id) == candidate
    assert repository.get(UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")) is None
