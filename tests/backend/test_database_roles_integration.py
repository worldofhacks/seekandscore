"""Optional real-Postgres proof of runtime role isolation and trigger-derived history."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command

from seekandscore.acquisition.models import (
    NormalizedParcelObservation,
    QuarantinedRecord,
    RawArtifact,
    SourceRun,
    SourceRunProfile,
    SourceRunStatus,
)
from seekandscore.acquisition.repository import PostgresAcquisitionRepository
from seekandscore.db.migrate import build_config
from seekandscore.db.release import DatabaseReleaseError, database_release_lock
from seekandscore.db.roles import (
    DEFAULT_API_LOGIN_ROLE,
    DEFAULT_INGESTION_LOGIN_ROLE,
    audit_api_runtime,
    audit_ingestion_runtime,
    provision_api_runtime,
    provision_ingestion_runtime,
)
from seekandscore.deal.models import ResearchCase, ResearchStatus
from seekandscore.deal.repository import (
    PostgresResearchCaseRepository,
    audit_event_table,
    research_case_revision_table,
)

TEST_DATABASE_URL = os.getenv("SEEKANDSCORE_TEST_DATABASE_URL")
API_PASSWORD = "ApiTestRolePassword_1234567890abcdef"
INGESTION_PASSWORD = "IngestionTestPassword_1234567890abcdef"


def _runtime_url(owner_url: str, username: str, password: str) -> str:
    return (
        sa.engine.make_url(owner_url)
        .set(
            username=username,
            password=password,
        )
        .render_as_string(hide_password=False)
    )


def _assert_privilege_denied(engine: sa.Engine, statement: str) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with pytest.raises(sa.exc.DBAPIError) as captured:
                connection.exec_driver_sql(statement)
            assert getattr(captured.value.orig, "sqlstate", None) == "42501"
        finally:
            transaction.rollback()


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="SEEKANDSCORE_TEST_DATABASE_URL is not set")
def test_database_release_lock_fails_closed_on_concurrent_session() -> None:
    assert TEST_DATABASE_URL is not None
    database_name = sa.engine.make_url(TEST_DATABASE_URL).database or ""
    if not database_name.endswith("_test"):
        pytest.fail("SEEKANDSCORE_TEST_DATABASE_URL must name a database ending in _test")

    with (
        database_release_lock(TEST_DATABASE_URL),
        pytest.raises(DatabaseReleaseError, match="already holds"),
        database_release_lock(TEST_DATABASE_URL),
    ):
        pytest.fail("contending release must never enter its critical section")

    # Closing the owning session releases the lock for the next deployment.
    with database_release_lock(TEST_DATABASE_URL):
        pass


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="SEEKANDSCORE_TEST_DATABASE_URL is not set")
def test_restricted_api_and_ingestion_roles_enforce_exact_contracts() -> None:
    assert TEST_DATABASE_URL is not None
    database_name = sa.engine.make_url(TEST_DATABASE_URL).database or ""
    if not database_name.endswith("_test"):
        pytest.fail("SEEKANDSCORE_TEST_DATABASE_URL must name a database ending in _test")

    command.upgrade(build_config(TEST_DATABASE_URL), "head")
    provision_api_runtime(TEST_DATABASE_URL, password=API_PASSWORD)
    provision_ingestion_runtime(TEST_DATABASE_URL, password=INGESTION_PASSWORD)
    api_url = _runtime_url(TEST_DATABASE_URL, DEFAULT_API_LOGIN_ROLE, API_PASSWORD)
    ingestion_url = _runtime_url(
        TEST_DATABASE_URL,
        DEFAULT_INGESTION_LOGIN_ROLE,
        INGESTION_PASSWORD,
    )

    assert audit_api_runtime(api_url).capability_role == "seekandscore_api_runtime"
    assert (
        audit_ingestion_runtime(ingestion_url).capability_role == "seekandscore_ingestion_runtime"
    )

    owner_engine = sa.create_engine(TEST_DATABASE_URL)
    api_engine = sa.create_engine(api_url)
    ingestion_engine = sa.create_engine(ingestion_url)
    organization_id = uuid4()
    actor_id = uuid4()
    case_id = uuid4()
    candidate_id = uuid4()
    backdated = datetime(2000, 1, 1, tzinfo=UTC)
    research_case = ResearchCase(
        id=case_id,
        organization_id=organization_id,
        candidate_id=candidate_id,
        region_id="us-tx-central-texas",
        jurisdiction_id="us-tx-travis",
        parcel_id=f"TCAD-{candidate_id.int}",
        status=ResearchStatus.WATCHING,
        operator_note="Restricted role integration proof",
        next_action="Verify access",
        candidate_read_model_version="role-test-v1",
        candidate_as_of=backdated,
        version=1,
        created_by=actor_id,
        updated_by=actor_id,
        created_at=backdated,
        updated_at=backdated,
    )

    try:
        research = PostgresResearchCaseRepository(api_engine)
        created, inserted = research.create(research_case)
        assert inserted is True
        updated_case = ResearchCase.model_validate(
            {
                **created.model_dump(),
                "status": ResearchStatus.RESEARCHING,
                "version": 2,
                "updated_at": datetime(2000, 1, 2, tzinfo=UTC),
            }
        )
        assert research.update(updated_case, expected_version=1) == updated_case

        with owner_engine.connect() as connection:
            revisions = connection.execute(
                sa.select(
                    research_case_revision_table.c.version,
                    research_case_revision_table.c.payload,
                    research_case_revision_table.c.recorded_at,
                )
                .where(research_case_revision_table.c.research_case_id == case_id)
                .order_by(research_case_revision_table.c.version)
            ).all()
            audits = connection.execute(
                sa.select(
                    audit_event_table.c.event_type,
                    audit_event_table.c.actor_id,
                    audit_event_table.c.details,
                    audit_event_table.c.recorded_at,
                )
                .where(
                    audit_event_table.c.organization_id == organization_id,
                    audit_event_table.c.subject_id == str(case_id),
                )
                .order_by(audit_event_table.c.recorded_at, audit_event_table.c.event_type)
            ).all()
        assert [row.version for row in revisions] == [1, 2]
        assert [row.payload["version"] for row in revisions] == [1, 2]
        assert all(row.recorded_at.year >= 2026 for row in revisions)
        assert {row.event_type for row in audits} == {
            "ResearchCaseCreated",
            "ResearchCaseUpdated",
        }
        assert all(row.actor_id == actor_id for row in audits)
        assert all(row.recorded_at.year >= 2026 for row in audits)

        _assert_privilege_denied(
            api_engine,
            "INSERT INTO deal.research_case_revision DEFAULT VALUES",
        )
        _assert_privilege_denied(api_engine, "INSERT INTO platform.audit_event DEFAULT VALUES")
        _assert_privilege_denied(
            api_engine,
            "UPDATE deal.research_case_revision SET version = version WHERE false",
        )
        _assert_privilege_denied(api_engine, "DELETE FROM platform.audit_event WHERE false")
        _assert_privilege_denied(api_engine, "CREATE TABLE deal.runtime_ddl_denied (id int)")

        acquisition = PostgresAcquisitionRepository(ingestion_engine)
        now = datetime.now(UTC)
        artifact_id = uuid4()
        observation_id = uuid4()
        run_id = uuid4()
        sha256 = artifact_id.hex * 2
        artifact = RawArtifact(
            id=artifact_id,
            source_id="role_contract_test",
            sha256=sha256,
            byte_count=2,
            media_type="application/json",
            storage_uri=f"s3://private-test/{sha256}.json",
            original_uri="https://example.invalid/role-test",
            request_params={},
            retrieved_at=now,
        )
        observation = NormalizedParcelObservation(
            id=observation_id,
            source_id="role_contract_test",
            source_record_id=str(observation_id),
            artifact_id=artifact_id,
            artifact_sha256=sha256,
            parser_version="role-test-v1",
            jurisdiction_id="us-tx-travis",
            local_parcel_id=str(observation_id),
            geographic_id=None,
            situs_address=None,
            situs_city=None,
            situs_zip=None,
            observed_at=now,
        )
        run = SourceRun(
            id=run_id,
            source_id="role_contract_test",
            status=SourceRunStatus.RUNNING,
            requested_at=now,
            started_at=now,
            adapter_version="role-test-v1",
            parser_version="role-test-v1",
            run_profile=SourceRunProfile.PROOF,
            configuration_hash="b" * 64,
            activation_id="role-test-only",
        )
        quarantine = QuarantinedRecord(
            id=uuid4(),
            source_id="role_contract_test",
            artifact_id=artifact_id,
            source_record_id="bad-record",
            reason_code="TEST_ONLY",
            reason_detail="Role integration proof",
            recorded_at=now,
        )
        acquisition.save_run(run)
        acquisition.save_run(run)
        acquisition.save_artifact(artifact)
        assert acquisition.save_observations((observation,)) == 1
        assert acquisition.save_quarantine((quarantine,)) == 1
        _assert_privilege_denied(
            ingestion_engine,
            "INSERT INTO deal.research_case DEFAULT VALUES",
        )
        _assert_privilege_denied(
            ingestion_engine,
            "UPDATE platform.audit_event SET event_type = event_type WHERE false",
        )
        _assert_privilege_denied(
            ingestion_engine,
            "CREATE TABLE observation.runtime_ddl_denied (id int)",
        )
    finally:
        api_engine.dispose()
        ingestion_engine.dispose()
        owner_engine.dispose()
