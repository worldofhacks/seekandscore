"""DB-independent live candidate and API provenance contract tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID, uuid5

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from seekandscore.acquisition.models import (
    NormalizedParcelObservation,
    RawArtifact,
    SourceDescriptor,
    SourceRun,
    SourceRunProfile,
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
from seekandscore.readmodels.live_candidates import LIVE_CANDIDATE_NAMESPACE
from seekandscore.registry import TRAVIS_TCAD_SOURCE, InMemorySourceRegistry

NOW = datetime(2026, 8, 13, 12, tzinfo=UTC)
SHA = "a" * 64
DISPLAY_APPROVAL_ID = "SRC-TCAD-TNR-BOUNDED-DISPLAY-20260813-V1"


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
            retrieved_at=NOW,
            records_fetched=1,
            observations_created=1,
            artifact_ids=(artifact.id,),
            adapter_version="travis-tcad-arcgis-v1",
            parser_version="travis-tcad-parcel-v1",
            run_profile=SourceRunProfile.COHORT,
            configuration_hash="d" * 64,
            activation_id="private-activation-id",
        )
    )
    return repository


def explorer_repository() -> MemoryAcquisitionRepository:
    repository = seeded_repository()
    original = next(iter(repository.observations.values()))
    repository.save_observations(
        (
            original.model_copy(
                update={
                    "id": UUID("11111111-1111-4111-8111-111111111111"),
                    "source_record_id": "102",
                    "local_parcel_id": "700002",
                    "situs_address": "200 MAIN ST MANOR 78653",
                    "situs_city": "MANOR",
                    "tcad_acres": 5.0,
                    "gis_acres": 4.98,
                }
            ),
            original.model_copy(
                update={
                    "id": UUID("22222222-2222-4222-8222-222222222222"),
                    "source_record_id": "103",
                    "local_parcel_id": "700003",
                    "situs_address": "300 AIRPORT COMMERCE DR DEL VALLE 78617",
                    "situs_city": "DEL VALLE",
                    "tcad_acres": 8.0,
                    "gis_acres": 7.96,
                }
            ),
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


def test_postgres_snapshot_queries_use_supported_sqlalchemy_json_accessors() -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalars.return_value.all.return_value = []
    connection.scalar.return_value = 0
    repository = PostgresAcquisitionRepository(engine)
    artifact_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

    assert (
        repository.latest_complete_run("travis_tcad_parcels", run_profile=SourceRunProfile.COHORT)
        is None
    )
    assert (
        repository.list_latest_observations(
            limit=25,
            artifact_ids=(artifact_id,),
            cities=("DEL VALLE", "MANOR"),
        )
        == ()
    )
    assert (
        repository.count_latest_observations(
            artifact_ids=(artifact_id,),
            cities=("DEL VALLE", "MANOR"),
        )
        == 0
    )


def test_postgres_latest_attempt_can_be_scoped_to_the_cohort_profile() -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalar.return_value = None

    result = PostgresAcquisitionRepository(engine).latest_run(
        "travis_tcad_parcels",
        run_profile=SourceRunProfile.COHORT,
    )

    assert result is None
    statement = connection.scalar.call_args.args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "run_profile" in compiled
    assert "cohort" in compiled


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
    assert "synthetic" not in candidate.model_dump()
    assert candidate.screening_only is True
    assert candidate.strategy == "assessor"
    assert candidate.opportunity_zone_status == "review"
    assert candidate.likely_basis == 0
    assert "no investment" in candidate.thesis
    assert candidate.source_observation is not None
    assert candidate.source_observation.fields.appraised_value_cents == 48_000_000
    assert candidate.source_observation.fields.assessed_value_cents == 45_000_000


def test_explorer_returns_filtered_and_full_cohort_totals_with_canonical_filters() -> None:
    repository = LiveCandidateRepository(
        explorer_repository(),
        InMemorySourceRegistry(),
        display_enabled=True,
    )

    page = repository.list(
        limit=25,
        cursor=None,
        dataset_mode="live",
        q="  main st  ",
        city="MANOR",
        min_acres=5,
        max_acres=5,
    )

    assert page.total == 1
    assert page.cohort_total == 3
    assert page.applied_filters.model_dump(mode="json") == {
        "q": "main st",
        "city": "MANOR",
        "min_acres": 5.0,
        "max_acres": 5.0,
    }
    candidate = page.items[0]
    assert candidate.parcel_id == "TCAD-700002"
    assert candidate.id == uuid5(LIVE_CANDIDATE_NAMESPACE, "us-tx-travis:700002")


@pytest.mark.parametrize(
    ("q", "city", "min_acres", "expected_parcel_id"),
    (
        ("700003", None, None, "TCAD-700003"),
        ("airport commerce", None, None, "TCAD-700003"),
        ("manor", None, None, "TCAD-700002"),
        (None, "DEL VALLE", 8.0, "TCAD-700003"),
    ),
)
def test_explorer_filters_only_approved_fields(
    q: str | None,
    city: str | None,
    min_acres: float | None,
    expected_parcel_id: str,
) -> None:
    repository = LiveCandidateRepository(
        explorer_repository(),
        InMemorySourceRegistry(),
        display_enabled=True,
    )

    page = repository.list(
        limit=25,
        cursor=None,
        dataset_mode="live",
        q=q,
        city=city,
        min_acres=min_acres,
    )

    assert page.total == 1
    assert page.cohort_total == 3
    assert page.items[0].parcel_id == expected_parcel_id


def test_explorer_zero_result_is_an_honest_current_filtered_page() -> None:
    repository = LiveCandidateRepository(
        explorer_repository(),
        InMemorySourceRegistry(),
        display_enabled=True,
    )

    page = repository.list(
        limit=25,
        cursor=None,
        dataset_mode="live",
        q="no such approved field value",
    )

    assert page.dataset_status == "current"
    assert page.items == ()
    assert page.total == 0
    assert page.cohort_total == 3
    assert page.applied_filters.q == "no such approved field value"


def test_explorer_cursor_is_bound_to_filters_and_complete_cohort() -> None:
    acquisition = explorer_repository()
    repository = LiveCandidateRepository(
        acquisition,
        InMemorySourceRegistry(),
        display_enabled=True,
    )
    first = repository.list(
        limit=1,
        cursor=None,
        dataset_mode="live",
        city="DEL VALLE",
    )
    assert first.next_cursor is not None

    second = repository.list(
        limit=1,
        cursor=first.next_cursor,
        dataset_mode="live",
        city="DEL VALLE",
    )

    assert [item.parcel_id for item in first.items] == ["TCAD-700003"]
    assert [item.parcel_id for item in second.items] == ["TCAD-700001"]
    with pytest.raises(ValueError, match="requested filters"):
        repository.list(
            limit=1,
            cursor=first.next_cursor,
            dataset_mode="live",
            city="MANOR",
        )

    current = acquisition.latest_complete_run(
        "travis_tcad_parcels", run_profile=SourceRunProfile.COHORT
    )
    assert current is not None
    acquisition.save_run(
        current.model_copy(
            update={
                "id": UUID("33333333-3333-4333-8333-333333333333"),
                "started_at": NOW + timedelta(minutes=1),
                "completed_at": NOW + timedelta(minutes=1),
                "retrieved_at": NOW + timedelta(minutes=1),
            }
        )
    )

    with pytest.raises(ValueError, match="current complete cohort"):
        repository.list(
            limit=1,
            cursor=first.next_cursor,
            dataset_mode="live",
            city="DEL VALLE",
        )


def test_postgres_explorer_builds_sql_filters_for_approved_fields_only() -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalars.return_value.all.return_value = []
    repository = PostgresAcquisitionRepository(engine)

    repository.list_latest_observations(
        limit=25,
        artifact_ids=(UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),),
        cities=("MANOR",),
        search_query="50%_TEST",
        min_acres=1,
        max_acres=10,
    )

    statement = connection.scalars.call_args.args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "situs_address" in compiled
    assert "local_parcel_id" in compiled
    assert "situs_city" in compiled
    assert "tcad_acres" in compiled
    assert "gis_acres" in compiled
    assert "py_owner" not in compiled


def test_live_projection_fails_closed_when_display_rights_are_not_approved() -> None:
    repository = LiveCandidateRepository(
        seeded_repository(),
        InMemorySourceRegistry(),
        display_enabled=False,
    )

    page = repository.list(limit=25, cursor=None, dataset_mode="live")

    assert page.items == ()
    assert page.dataset_status == "error"
    assert page.sources[0].status == "unavailable"
    assert "runtime approval gates" in page.warnings[0]


def test_container_requires_runtime_display_flag_even_when_source_allows_display() -> None:
    settings = Settings(
        app_env="test",
        dataset_mode="live",
        database_url="sqlite://",
    )
    container = AppContainer.build(settings)

    page = container.candidates.list(limit=25, cursor=None, dataset_mode="live")

    assert page.items == ()
    assert page.dataset_status == "error"
    assert container.candidates.display_enabled is False
    assert "runtime approval gates" in page.warnings[0]


def test_container_accepts_only_recorded_display_approval() -> None:
    settings = Settings(
        app_env="test",
        dataset_mode="live",
        database_url="sqlite://",
        live_source_display_enabled=True,
        live_source_display_approval_id=DISPLAY_APPROVAL_ID,
    )

    container = AppContainer.build(settings)

    assert container.candidates.display_enabled is True


def test_source_display_default_is_false_and_tcad_scope_is_explicit() -> None:
    assert SourceDescriptor.model_fields["display_allowed"].default is False
    assert TRAVIS_TCAD_SOURCE.display_allowed is True
    assert TRAVIS_TCAD_SOURCE.export_allowed is False
    assert TRAVIS_TCAD_SOURCE.redistribution_allowed is False
    assert TRAVIS_TCAD_SOURCE.terms_uri.endswith("/MapServer/info/iteminfo")


def test_repository_cannot_override_source_display_prohibition() -> None:
    source = TRAVIS_TCAD_SOURCE.model_copy(update={"display_allowed": False})
    repository = LiveCandidateRepository(
        seeded_repository(),
        InMemorySourceRegistry((source,)),
        display_enabled=True,
    )

    page = repository.list(limit=25, cursor=None, dataset_mode="live")

    assert repository.display_enabled is False
    assert page.dataset_status == "error"
    assert page.items == ()


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
    assert response.json()["source"]["display_allowed"] is True
    assert response.json()["source"]["export_allowed"] is False
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
                "run_profile": SourceRunProfile.PROOF,
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

    assert page.dataset_status == "current"
    assert page.partial is False
    assert repository.get(candidate.id) == candidate
    assert repository.get(UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")) is None


def test_failed_refresh_observations_do_not_leak_into_last_complete_snapshot() -> None:
    acquisition = seeded_repository()
    original = next(iter(acquisition.observations.values()))
    failed_artifact = RawArtifact(
        id=UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
        source_id="travis_tcad_parcels",
        sha256="e" * 64,
        byte_count=100,
        media_type="application/json",
        storage_uri="s3://private/failed.json",
        original_uri="https://example.invalid/query",
        request_params={},
        retrieved_at=NOW + timedelta(days=1),
    )
    acquisition.save_artifact(failed_artifact)
    acquisition.save_observations(
        (
            original.model_copy(
                update={
                    "id": UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
                    "source_record_id": "999",
                    "local_parcel_id": "999999",
                    "artifact_id": failed_artifact.id,
                    "artifact_sha256": failed_artifact.sha256,
                    "observed_at": failed_artifact.retrieved_at,
                }
            ),
        )
    )
    complete = acquisition.latest_complete_run(
        "travis_tcad_parcels", run_profile=SourceRunProfile.COHORT
    )
    assert complete is not None
    acquisition.save_run(
        complete.model_copy(
            update={
                "id": UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
                "status": SourceRunStatus.FAILED,
                "started_at": failed_artifact.retrieved_at,
                "completed_at": failed_artifact.retrieved_at,
                "retrieved_at": failed_artifact.retrieved_at,
                "artifact_ids": (failed_artifact.id,),
                "partial": True,
                "error_code": "IncompleteCohortError",
            }
        )
    )
    failed_cohort = acquisition.latest_run(
        "travis_tcad_parcels", run_profile=SourceRunProfile.COHORT
    )
    assert failed_cohort is not None
    acquisition.save_run(
        failed_cohort.model_copy(
            update={
                "id": UUID("abababab-abab-4bab-8bab-abababababab"),
                "status": SourceRunStatus.PARTIAL,
                "run_profile": SourceRunProfile.PROOF,
                "started_at": failed_artifact.retrieved_at + timedelta(minutes=1),
                "completed_at": failed_artifact.retrieved_at + timedelta(minutes=1),
                "retrieved_at": failed_artifact.retrieved_at + timedelta(minutes=1),
                "records_fetched": 2,
                "partial": True,
                "error_code": None,
            }
        )
    )

    page = LiveCandidateRepository(
        acquisition, InMemorySourceRegistry(), display_enabled=True
    ).list(limit=25, cursor=None, dataset_mode="live")

    assert page.total == 1
    assert page.items[0].parcel_id == "TCAD-700001"
    assert page.dataset_status == "stale"
    assert page.sources[0].status == "error"
    assert "last complete snapshot" in page.warnings[0]
    assert page.items[0].evidence.freshness == "stale"
    assert (
        LiveCandidateRepository(acquisition, InMemorySourceRegistry(), display_enabled=True).get(
            page.items[0].id
        )
        == page.items[0]
    )


def test_running_cohort_refresh_keeps_last_complete_snapshot_current() -> None:
    acquisition = seeded_repository()
    complete = acquisition.latest_complete_run(
        "travis_tcad_parcels", run_profile=SourceRunProfile.COHORT
    )
    assert complete is not None
    acquisition.save_run(
        complete.model_copy(
            update={
                "id": UUID("acacacac-acac-4cac-8cac-acacacacacac"),
                "status": SourceRunStatus.RUNNING,
                "started_at": NOW + timedelta(minutes=1),
                "completed_at": None,
                "retrieved_at": None,
                "records_fetched": 0,
                "observations_created": 0,
                "artifact_ids": (),
            }
        )
    )
    repository = LiveCandidateRepository(
        acquisition,
        InMemorySourceRegistry(),
        display_enabled=True,
    )

    page = repository.list(limit=25, cursor=None, dataset_mode="live")

    assert page.dataset_status == "current"
    assert page.sources[0].status == "current"
    assert not any("refresh failed" in warning for warning in page.warnings)
    assert page.items[0].evidence.freshness == "current"
    assert repository.get(page.items[0].id) == page.items[0]


def test_new_complete_snapshot_removes_parcels_absent_from_refresh() -> None:
    acquisition = seeded_repository()
    original = next(iter(acquisition.observations.values()))
    old_removed = original.model_copy(
        update={
            "id": UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
            "source_record_id": "102",
            "local_parcel_id": "700002",
        }
    )
    acquisition.save_observations((old_removed,))
    refreshed_artifact = RawArtifact(
        id=UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
        source_id="travis_tcad_parcels",
        sha256="f" * 64,
        byte_count=100,
        media_type="application/json",
        storage_uri="s3://private/refreshed.json",
        original_uri="https://example.invalid/query",
        request_params={},
        retrieved_at=NOW + timedelta(days=1),
    )
    acquisition.save_artifact(refreshed_artifact)
    refreshed = original.model_copy(
        update={
            "id": UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
            "artifact_id": refreshed_artifact.id,
            "artifact_sha256": refreshed_artifact.sha256,
            "observed_at": refreshed_artifact.retrieved_at,
        }
    )
    acquisition.save_observations((refreshed,))
    current = acquisition.latest_complete_run(
        "travis_tcad_parcels", run_profile=SourceRunProfile.COHORT
    )
    assert current is not None
    acquisition.save_run(
        current.model_copy(
            update={
                "id": UUID("11111111-1111-4111-8111-111111111111"),
                "started_at": refreshed_artifact.retrieved_at,
                "completed_at": refreshed_artifact.retrieved_at,
                "retrieved_at": refreshed_artifact.retrieved_at,
                "records_fetched": 1,
                "observations_created": 1,
                "artifact_ids": (refreshed_artifact.id,),
            }
        )
    )

    page = LiveCandidateRepository(
        acquisition, InMemorySourceRegistry(), display_enabled=True
    ).list(limit=25, cursor=None, dataset_mode="live")

    assert page.total == 1
    assert [item.parcel_id for item in page.items] == ["TCAD-700001"]
    assert page.retrieved_at == refreshed_artifact.retrieved_at


def test_live_projection_rejects_malformed_cursor() -> None:
    repository = LiveCandidateRepository(
        seeded_repository(),
        InMemorySourceRegistry(),
        display_enabled=True,
    )

    with pytest.raises(ValueError, match="cursor is malformed"):
        repository.list(limit=1, cursor="not-a-cursor", dataset_mode="live")


def test_live_candidate_api_serves_only_durable_projection_and_validates_cursor() -> None:
    settings = Settings(app_env="test")
    app = create_app(settings)
    container = AppContainer.build(settings)
    object.__setattr__(
        container,
        "candidates",
        LiveCandidateRepository(
            seeded_repository(),
            InMemorySourceRegistry(),
            display_enabled=True,
        ),
    )
    app.dependency_overrides[get_container] = lambda: container

    with TestClient(app) as live_client:
        response = live_client.get("/v1/candidates")
        malformed = live_client.get("/v1/candidates", params={"cursor": "not-a-cursor"})
        candidate_id = response.json()["items"][0]["id"]
        detail = live_client.get(f"/v1/candidates/{candidate_id}")

    assert response.status_code == 200
    assert response.json()["dataset_mode"] == "live"
    assert response.json()["total"] == 1
    assert "synthetic" not in response.text.lower()
    assert response.headers["etag"].startswith('"live-assessor-explorer-v2:')
    assert malformed.status_code == 400
    assert malformed.json()["detail"] == "cursor is malformed"
    assert detail.status_code == 200


def test_live_candidate_api_validates_and_echoes_explorer_query() -> None:
    settings = Settings(app_env="test")
    app = create_app(settings)
    container = AppContainer.build(settings)
    object.__setattr__(
        container,
        "candidates",
        LiveCandidateRepository(
            explorer_repository(),
            InMemorySourceRegistry(),
            display_enabled=True,
        ),
    )
    app.dependency_overrides[get_container] = lambda: container

    with TestClient(app) as live_client:
        response = live_client.get(
            "/v1/candidates",
            params={
                "q": " main ",
                "city": "MANOR",
                "min_acres": 5,
                "max_acres": 5,
            },
        )
        invalid_city = live_client.get("/v1/candidates", params={"city": "AUSTIN"})
        invalid_range = live_client.get("/v1/candidates", params={"min_acres": 10, "max_acres": 1})
        overlong_query = live_client.get("/v1/candidates", params={"q": "x" * 101})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["cohort_total"] == 3
    assert response.json()["applied_filters"] == {
        "q": "main",
        "city": "MANOR",
        "min_acres": 5.0,
        "max_acres": 5.0,
    }
    assert invalid_city.status_code == 422
    assert invalid_range.status_code == 422
    assert overlong_query.status_code == 422


def test_live_candidate_etag_is_evaluated_after_projection_availability() -> None:
    settings = Settings(app_env="test")
    app = create_app(settings)
    container = AppContainer.build(settings)
    object.__setattr__(
        container,
        "candidates",
        LiveCandidateRepository(
            seeded_repository(),
            InMemorySourceRegistry(),
            display_enabled=True,
        ),
    )
    app.dependency_overrides[get_container] = lambda: container

    with TestClient(app) as live_client:
        initial = live_client.get("/v1/candidates")
        cached = live_client.get(
            "/v1/candidates",
            headers={"If-None-Match": initial.headers["etag"]},
        )

    assert initial.status_code == 200
    assert cached.status_code == 304
    assert cached.content == b""
