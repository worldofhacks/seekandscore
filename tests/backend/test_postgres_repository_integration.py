"""Optional real-Postgres regression for JSON-backed live snapshot queries."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa

from seekandscore.acquisition.models import (
    NormalizedParcelObservation,
    RawArtifact,
    SourceRun,
    SourceRunProfile,
    SourceRunStatus,
)
from seekandscore.acquisition.repository import (
    PostgresAcquisitionRepository,
    observation_table,
    raw_artifact_table,
    source_run_table,
)
from seekandscore.readmodels import LiveCandidateRepository
from seekandscore.registry import InMemorySourceRegistry

TEST_DATABASE_URL = os.getenv("SEEKANDSCORE_TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="SEEKANDSCORE_TEST_DATABASE_URL is not set")
def test_artifact_scoped_snapshot_queries_execute_on_postgres() -> None:
    assert TEST_DATABASE_URL is not None
    database_name = sa.engine.make_url(TEST_DATABASE_URL).database or ""
    if not database_name.endswith("_test"):
        pytest.fail("SEEKANDSCORE_TEST_DATABASE_URL must name a database ending in _test")

    engine = sa.create_engine(TEST_DATABASE_URL)
    repository = PostgresAcquisitionRepository(engine)
    now = datetime.now(UTC)
    artifact_id = uuid4()
    observation_id = uuid4()
    run_id = uuid4()
    sha256 = artifact_id.hex * 2
    artifact = RawArtifact(
        id=artifact_id,
        source_id="travis_tcad_parcels",
        sha256=sha256,
        byte_count=2,
        media_type="application/json",
        storage_uri=f"s3://private-test/{sha256}.json",
        original_uri="https://example.invalid/query",
        request_params={},
        retrieved_at=now,
    )
    observation = NormalizedParcelObservation(
        id=observation_id,
        source_id="travis_tcad_parcels",
        source_record_id=str(observation_id.int),
        artifact_id=artifact_id,
        artifact_sha256=sha256,
        parser_version="travis-tcad-parcel-v1",
        jurisdiction_id="us-tx-travis",
        local_parcel_id=str(observation_id.int),
        geographic_id=None,
        situs_address="100 TEST RD",
        situs_city="DEL VALLE",
        situs_zip="78617",
        tcad_acres=2.0,
        observed_at=now,
    )
    run = SourceRun(
        id=run_id,
        source_id="travis_tcad_parcels",
        status=SourceRunStatus.SUCCEEDED,
        requested_at=now,
        started_at=now,
        completed_at=now,
        retrieved_at=now,
        records_fetched=1,
        observations_created=1,
        artifact_ids=(artifact_id,),
        adapter_version="travis-tcad-arcgis-v1",
        parser_version="travis-tcad-parcel-v1",
        run_profile=SourceRunProfile.COHORT,
        configuration_hash="a" * 64,
        activation_id="test-only",
    )

    try:
        repository.save_artifact(artifact)
        assert repository.save_observations((observation,)) == 1
        repository.save_run(run)

        assert (
            repository.latest_complete_run(
                "travis_tcad_parcels", run_profile=SourceRunProfile.COHORT
            )
            == run
        )
        assert repository.list_latest_observations(
            limit=25,
            artifact_ids=(artifact_id,),
            cities=("DEL VALLE", "MANOR"),
        ) == (observation,)
        assert (
            repository.count_latest_observations(
                artifact_ids=(artifact_id,),
                cities=("DEL VALLE", "MANOR"),
            )
            == 1
        )
        candidates = LiveCandidateRepository(
            repository,
            InMemorySourceRegistry(),
            display_enabled=True,
        )
        page = candidates.list(limit=25, cursor=None, dataset_mode="live")
        assert page.dataset_status == "current"
        assert page.total == 1
        assert len(page.items) == 1
        assert candidates.get(page.items[0].id) == page.items[0]
    finally:
        with engine.begin() as connection:
            connection.execute(sa.delete(source_run_table).where(source_run_table.c.id == run_id))
            connection.execute(
                sa.delete(observation_table).where(observation_table.c.id == observation_id)
            )
            connection.execute(
                sa.delete(raw_artifact_table).where(raw_artifact_table.c.id == artifact_id)
            )
        engine.dispose()
