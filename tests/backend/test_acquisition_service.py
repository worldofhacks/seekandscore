"""Replay, immutability, failure, and partial-run tests."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from seekandscore.acquisition.adapters import TravisTcadArcGisAdapter, TravisTcadQuery
from seekandscore.acquisition.models import (
    AcquisitionCompletenessPolicy,
    SourceRunProfile,
    SourceRunStatus,
)
from seekandscore.acquisition.repository import MemoryAcquisitionRepository
from seekandscore.acquisition.service import AcquisitionService, IngestionDisabledError
from seekandscore.acquisition.store import FileArtifactStore
from seekandscore.registry.sources import TRAVIS_TCAD_ACQUISITION_APPROVAL_ID

FIXTURE = Path(__file__).parent / "fixtures" / "tcad_page.json"


def build_service(
    tmp_path: Path,
    repository: MemoryAcquisitionRepository,
    *,
    count: int = 2,
    count_responses: list[int] | None = None,
    page_content: bytes | None = None,
    max_records: int = 2,
    page_size: int | None = None,
    page_contents: dict[int, bytes] | None = None,
    responses: list[tuple[int, dict[str, str]]] | None = None,
    transport_failures: int = 0,
    sleeps: list[float] | None = None,
    min_request_interval_seconds: float = 0,
    run_profile: SourceRunProfile = SourceRunProfile.PROOF,
    completeness_policy: AcquisitionCompletenessPolicy = (
        AcquisitionCompletenessPolicy.ALLOW_BOUNDED_PARTIAL
    ),
) -> tuple[AcquisitionService, list[httpx.Request]]:
    requests: list[httpx.Request] = []
    content = page_content or FIXTURE.read_bytes()
    failures_remaining = transport_failures

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal failures_remaining
        requests.append(request)
        if failures_remaining:
            failures_remaining -= 1
            raise httpx.ConnectError("temporary connection failure", request=request)
        if responses:
            status, headers = responses.pop(0)
            if status != 200:
                return httpx.Response(status, headers=headers, text="retry")
        if request.url.params.get("returnCountOnly") == "true":
            response_count = count_responses.pop(0) if count_responses else count
            return httpx.Response(200, json={"count": response_count})
        offset = int(request.url.params.get("resultOffset", "0"))
        return httpx.Response(
            200,
            content=(page_contents or {}).get(offset, content),
            headers={"Content-Type": "application/json", "ETag": '"fixture-etag"'},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = AcquisitionService(
        adapter=TravisTcadArcGisAdapter(
            TravisTcadQuery(
                page_size=page_size or max_records,
                max_records=max_records,
                cities=("DEL VALLE", "MANOR"),
                run_profile=run_profile,
                completeness_policy=completeness_policy,
            )
        ),
        repository=repository,
        artifact_store=FileArtifactStore(tmp_path),
        http_client=client,
        clock=lambda: datetime(2026, 8, 13, 12, tzinfo=UTC),
        sleeper=(sleeps.append if sleeps is not None else lambda _seconds: None),
        min_request_interval_seconds=min_request_interval_seconds,
    )
    return service, requests


def execute(service: AcquisitionService):  # type: ignore[no-untyped-def]
    return service.execute(
        ingestion_enabled=True,
        dataset_mode="live",
        activation_id=TRAVIS_TCAD_ACQUISITION_APPROVAL_ID,
    )


def test_three_replays_create_one_artifact_and_one_observation_version(tmp_path: Path) -> None:
    repository = MemoryAcquisitionRepository()
    service, requests = build_service(tmp_path, repository)

    runs = tuple(execute(service) for _ in range(3))

    assert all(run.status is SourceRunStatus.SUCCEEDED for run in runs)
    assert [run.observations_created for run in runs] == [2, 0, 0]
    assert len(repository.artifacts) == 1
    assert len(repository.observations) == 2
    assert len(repository.runs) == 3
    assert len(requests) == 6
    artifact = next(iter(repository.artifacts.values()))
    assert artifact.sha256 == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert artifact.response_etag == '"fixture-etag"'
    assert Path(artifact.storage_uri.removeprefix("file://")).read_bytes() == FIXTURE.read_bytes()


def test_count_above_cap_marks_run_partial(tmp_path: Path) -> None:
    repository = MemoryAcquisitionRepository()
    service, _ = build_service(tmp_path, repository, count=3, max_records=2)

    run = execute(service)

    assert run.status is SourceRunStatus.PARTIAL
    assert run.partial is True
    assert run.records_fetched == 2


def test_complete_cohort_fails_before_page_or_artifact_when_count_exceeds_cap(
    tmp_path: Path,
) -> None:
    repository = MemoryAcquisitionRepository()
    service, requests = build_service(
        tmp_path,
        repository,
        count=1001,
        max_records=1000,
        page_size=250,
        run_profile=SourceRunProfile.COHORT,
        completeness_policy=AcquisitionCompletenessPolicy.REQUIRE_COMPLETE,
    )

    run = execute(service)

    assert run.status is SourceRunStatus.FAILED
    assert run.error_code == "IncompleteCohortError"
    assert run.records_fetched == 0
    assert run.artifact_ids == ()
    assert len(requests) == 1
    assert not repository.artifacts


def test_complete_cohort_rechecks_count_after_all_pages(tmp_path: Path) -> None:
    repository = MemoryAcquisitionRepository()
    service, requests = build_service(
        tmp_path,
        repository,
        count=2,
        max_records=1000,
        page_size=250,
        run_profile=SourceRunProfile.COHORT,
        completeness_policy=AcquisitionCompletenessPolicy.REQUIRE_COMPLETE,
    )

    run = execute(service)

    assert run.status is SourceRunStatus.SUCCEEDED
    assert run.run_profile is SourceRunProfile.COHORT
    assert run.partial is False
    assert [request.url.params.get("returnCountOnly") for request in requests] == [
        "true",
        None,
        "true",
    ]


def test_complete_cohort_fails_if_count_changes_during_acquisition(tmp_path: Path) -> None:
    repository = MemoryAcquisitionRepository()
    service, _ = build_service(
        tmp_path,
        repository,
        count_responses=[2, 3],
        max_records=1000,
        page_size=250,
        run_profile=SourceRunProfile.COHORT,
        completeness_policy=AcquisitionCompletenessPolicy.REQUIRE_COMPLETE,
    )

    run = execute(service)

    assert run.status is SourceRunStatus.FAILED
    assert run.error_code == "IncompleteCohortError"
    assert run.records_fetched == 2
    assert run.partial is True


def test_count_drives_bounded_pagination_even_when_transfer_flag_is_false(
    tmp_path: Path,
) -> None:
    first_page = FIXTURE.read_bytes()
    second_page = (
        FIXTURE.read_text()
        .replace('"OBJECTID": 101', '"OBJECTID": 201')
        .replace('"OBJECTID": 102', '"OBJECTID": 202')
        .replace('"PROP_ID": 700001', '"PROP_ID": 800001')
        .replace('"PROP_ID": 700002', '"PROP_ID": 800002')
        .encode()
    )
    repository = MemoryAcquisitionRepository()
    service, requests = build_service(
        tmp_path,
        repository,
        count=4,
        page_size=2,
        max_records=4,
        page_contents={0: first_page, 2: second_page},
    )

    run = execute(service)

    assert run.status is SourceRunStatus.SUCCEEDED
    assert run.records_fetched == 4
    assert run.observations_created == 4
    assert len(repository.artifacts) == 2
    assert [request.url.params.get("resultOffset") for request in requests[1:]] == ["0", "2"]


def test_short_page_is_reported_as_partial_instead_of_success(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_bytes())
    payload["features"] = payload["features"][:1]
    one_feature = json.dumps(payload).encode()
    repository = MemoryAcquisitionRepository()
    service, _ = build_service(
        tmp_path,
        repository,
        count=4,
        page_content=one_feature,
        page_size=2,
        max_records=4,
    )

    run = execute(service)

    assert run.status is SourceRunStatus.PARTIAL
    assert run.partial is True
    assert run.records_fetched == 1


def test_schema_drift_preserves_raw_artifact_and_records_failed_run(tmp_path: Path) -> None:
    invalid = (
        FIXTURE.read_text()
        .replace(
            '"name": "PROP_ID", "type": "esriFieldTypeInteger"',
            '"name": "PROP_ID", "type": "esriFieldTypeString"',
        )
        .encode()
    )
    repository = MemoryAcquisitionRepository()
    service, _ = build_service(tmp_path, repository, page_content=invalid)

    run = execute(service)

    assert run.status is SourceRunStatus.FAILED
    assert run.error_code == "SourceSchemaError"
    assert len(repository.artifacts) == 1
    assert not repository.observations


def test_external_acquisition_gate_prevents_network_or_storage(tmp_path: Path) -> None:
    repository = MemoryAcquisitionRepository()
    service, requests = build_service(tmp_path, repository)

    with pytest.raises(IngestionDisabledError, match="INGESTION_ENABLED"):
        service.execute(
            ingestion_enabled=False,
            dataset_mode="synthetic",
            activation_id=None,
        )

    assert not requests
    assert not repository.artifacts
    assert not repository.runs


@pytest.mark.parametrize("activation_id", [None, "arbitrary-nonempty-approval"])
def test_exact_activation_record_is_required_even_when_live_flags_are_on(
    tmp_path: Path,
    activation_id: str | None,
) -> None:
    service, requests = build_service(tmp_path, MemoryAcquisitionRepository())

    with pytest.raises(IngestionDisabledError, match="approved source acquisition record"):
        service.execute(
            ingestion_enabled=True,
            dataset_mode="live",
            activation_id=activation_id,
        )

    assert not requests


def test_retry_after_and_bounded_retry_policy(tmp_path: Path) -> None:
    sleeps: list[float] = []
    service, requests = build_service(
        tmp_path,
        MemoryAcquisitionRepository(),
        responses=[(429, {"Retry-After": "2.5"}), (200, {}), (200, {})],
        sleeps=sleeps,
    )

    run = execute(service)

    assert run.status is SourceRunStatus.SUCCEEDED
    assert len(requests) == 3
    assert 2.5 in sleeps


def test_transport_failure_is_retried_with_backoff(tmp_path: Path) -> None:
    sleeps: list[float] = []
    service, requests = build_service(
        tmp_path,
        MemoryAcquisitionRepository(),
        transport_failures=1,
        sleeps=sleeps,
    )

    run = execute(service)

    assert run.status is SourceRunStatus.SUCCEEDED
    assert len(requests) == 3
    assert 1.0 in sleeps


def test_requests_are_spaced_after_each_completed_request(tmp_path: Path) -> None:
    sleeps: list[float] = []
    service, _ = build_service(
        tmp_path,
        MemoryAcquisitionRepository(),
        sleeps=sleeps,
        min_request_interval_seconds=1,
    )

    run = execute(service)

    assert run.status is SourceRunStatus.SUCCEEDED
    assert sleeps == [1.0]


def test_invalid_count_response_records_failure(tmp_path: Path) -> None:
    repository = MemoryAcquisitionRepository()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": 2})

    service = AcquisitionService(
        adapter=TravisTcadArcGisAdapter(TravisTcadQuery(max_records=2)),
        repository=repository,
        artifact_store=FileArtifactStore(tmp_path),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: datetime(2026, 8, 13, 12, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        min_request_interval_seconds=0,
    )

    run = execute(service)

    assert run.status is SourceRunStatus.FAILED
    assert run.error_code == "SourceSchemaError"
