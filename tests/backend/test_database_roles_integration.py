"""Optional real-Postgres proof of runtime role isolation and trigger-derived history."""

import json
import os
from datetime import UTC, date, datetime
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
    DEFAULT_OZ_IMPORTER_LOGIN_ROLE,
    DEFAULT_OZ_MEMBERSHIP_LOGIN_ROLE,
    OZ_IMPORTER_RUNTIME_CAPABILITY_ROLE,
    OZ_MEMBERSHIP_RUNTIME_CAPABILITY_ROLE,
    DatabaseRoleAuditError,
    audit_api_runtime,
    audit_ingestion_runtime,
    audit_oz_importer_runtime,
    audit_oz_membership_runtime,
    provision_api_runtime,
    provision_ingestion_runtime,
    provision_oz_importer_runtime,
    provision_oz_membership_runtime,
)
from seekandscore.deal.models import ResearchCase, ResearchStatus
from seekandscore.deal.repository import (
    PostgresResearchCaseRepository,
    audit_event_table,
    research_case_revision_table,
)
from seekandscore.geography.opportunity_zones.models import (
    OpportunityZoneImportRun,
    OpportunityZoneImportStatus,
)
from seekandscore.geography.opportunity_zones.repository import (
    PostgresOpportunityZoneRepository,
)
from seekandscore.identity import canonical_parcel_id

TEST_DATABASE_URL = os.getenv("SEEKANDSCORE_TEST_DATABASE_URL")
API_PASSWORD = "ApiTestRolePassword_1234567890abcdef"
INGESTION_PASSWORD = "IngestionTestPassword_1234567890abcdef"
OZ_IMPORTER_PASSWORD = "OzImporterTestPassword_1234567890abcdef"
OZ_MEMBERSHIP_PASSWORD = "OzMembershipTestPassword_1234567890abcdef"


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


def _assert_database_rejected(
    engine: sa.Engine,
    statement: str,
    *,
    parameters: dict[str, object] | None = None,
    sqlstates: frozenset[str],
) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with pytest.raises(sa.exc.DBAPIError) as captured:
                connection.execute(sa.text(statement), parameters or {})
            assert getattr(captured.value.orig, "sqlstate", None) in sqlstates
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
def test_oz_capability_roles_are_inert_after_membership_migration_downgrade() -> None:
    assert TEST_DATABASE_URL is not None
    database_name = sa.engine.make_url(TEST_DATABASE_URL).database or ""
    if not database_name.endswith("_test"):
        pytest.fail("SEEKANDSCORE_TEST_DATABASE_URL must name a database ending in _test")

    config = build_config(TEST_DATABASE_URL)
    command.upgrade(config, "head")
    capability_roles = (
        OZ_IMPORTER_RUNTIME_CAPABILITY_ROLE,
        OZ_MEMBERSHIP_RUNTIME_CAPABILITY_ROLE,
    )
    try:
        command.downgrade(config, "20260813_0006")
        engine = sa.create_engine(TEST_DATABASE_URL)
        try:
            with engine.connect() as connection:
                table_grants = int(
                    connection.scalar(
                        sa.text(
                            "SELECT count(*) FROM information_schema.role_table_grants "
                            "WHERE grantee = ANY(:roles)"
                        ),
                        {"roles": list(capability_roles)},
                    )
                    or 0
                )
                column_grants = int(
                    connection.scalar(
                        sa.text(
                            "SELECT count(*) FROM information_schema.column_privileges "
                            "WHERE grantee = ANY(:roles)"
                        ),
                        {"roles": list(capability_roles)},
                    )
                    or 0
                )
                schema_grants = int(
                    connection.scalar(
                        sa.text(
                            """
                            SELECT count(*)
                            FROM pg_namespace AS n
                            CROSS JOIN LATERAL aclexplode(
                                COALESCE(n.nspacl, acldefault('n', n.nspowner))
                            ) AS acl
                            JOIN pg_roles AS grantee ON grantee.oid = acl.grantee
                            WHERE grantee.rolname = ANY(:roles)
                            """
                        ),
                        {"roles": list(capability_roles)},
                    )
                    or 0
                )
                database_grants = int(
                    connection.scalar(
                        sa.text(
                            """
                            SELECT count(*)
                            FROM pg_database AS d
                            CROSS JOIN LATERAL aclexplode(
                                COALESCE(d.datacl, acldefault('d', d.datdba))
                            ) AS acl
                            JOIN pg_roles AS grantee ON grantee.oid = acl.grantee
                            WHERE d.datname = current_database()
                              AND grantee.rolname = ANY(:roles)
                            """
                        ),
                        {"roles": list(capability_roles)},
                    )
                    or 0
                )
        finally:
            engine.dispose()
        assert (table_grants, column_grants, schema_grants, database_grants) == (0, 0, 0, 0)
    finally:
        command.upgrade(config, "head")


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="SEEKANDSCORE_TEST_DATABASE_URL is not set")
def test_restricted_api_and_ingestion_roles_enforce_exact_contracts() -> None:
    assert TEST_DATABASE_URL is not None
    database_name = sa.engine.make_url(TEST_DATABASE_URL).database or ""
    if not database_name.endswith("_test"):
        pytest.fail("SEEKANDSCORE_TEST_DATABASE_URL must name a database ending in _test")

    command.upgrade(build_config(TEST_DATABASE_URL), "head")
    provision_api_runtime(TEST_DATABASE_URL, password=API_PASSWORD)
    provision_ingestion_runtime(TEST_DATABASE_URL, password=INGESTION_PASSWORD)
    provision_oz_importer_runtime(TEST_DATABASE_URL, password=OZ_IMPORTER_PASSWORD)
    provision_oz_membership_runtime(TEST_DATABASE_URL, password=OZ_MEMBERSHIP_PASSWORD)
    api_url = _runtime_url(TEST_DATABASE_URL, DEFAULT_API_LOGIN_ROLE, API_PASSWORD)
    ingestion_url = _runtime_url(
        TEST_DATABASE_URL,
        DEFAULT_INGESTION_LOGIN_ROLE,
        INGESTION_PASSWORD,
    )
    oz_importer_url = _runtime_url(
        TEST_DATABASE_URL,
        DEFAULT_OZ_IMPORTER_LOGIN_ROLE,
        OZ_IMPORTER_PASSWORD,
    )
    oz_membership_url = _runtime_url(
        TEST_DATABASE_URL,
        DEFAULT_OZ_MEMBERSHIP_LOGIN_ROLE,
        OZ_MEMBERSHIP_PASSWORD,
    )

    assert audit_api_runtime(api_url).capability_role == "seekandscore_api_runtime"
    assert (
        audit_ingestion_runtime(ingestion_url).capability_role == "seekandscore_ingestion_runtime"
    )
    assert (
        audit_oz_importer_runtime(oz_importer_url).capability_role
        == "seekandscore_oz_importer_runtime"
    )
    assert (
        audit_oz_membership_runtime(oz_membership_url).capability_role
        == "seekandscore_oz_membership_runtime"
    )

    owner_engine = sa.create_engine(TEST_DATABASE_URL)
    api_engine = sa.create_engine(api_url)
    ingestion_engine = sa.create_engine(ingestion_url)
    oz_importer_engine = sa.create_engine(oz_importer_url)
    oz_membership_engine = sa.create_engine(oz_membership_url)
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
        trigger_audits = (
            (
                "geo.opportunity_zone_import_run",
                "trg_oz_import_run_validate_transition",
                lambda: audit_oz_importer_runtime(oz_importer_url),
            ),
            (
                "geo.opportunity_zone_membership_build_run",
                "trg_oz_membership_build_validate_transition",
                lambda: audit_oz_membership_runtime(oz_membership_url),
            ),
            (
                "geo.opportunity_zone_membership",
                "trg_oz_membership_validate_geometry_lineage",
                lambda: audit_oz_membership_runtime(oz_membership_url),
            ),
        )
        for relation, trigger, audit in trigger_audits:
            with owner_engine.begin() as connection:
                connection.exec_driver_sql(f"ALTER TABLE {relation} DISABLE TRIGGER {trigger}")
            try:
                with pytest.raises(DatabaseRoleAuditError, match="required trigger"):
                    audit()
            finally:
                with owner_engine.begin() as connection:
                    connection.exec_driver_sql(f"ALTER TABLE {relation} ENABLE TRIGGER {trigger}")

        with owner_engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP TRIGGER trg_oz_membership_validate_geometry_lineage "
                "ON geo.opportunity_zone_membership"
            )
            connection.exec_driver_sql(
                "CREATE TRIGGER trg_oz_membership_validate_geometry_lineage "
                "BEFORE UPDATE ON geo.opportunity_zone_membership FOR EACH ROW "
                "EXECUTE FUNCTION geo.validate_oz_membership_geometry_lineage()"
            )
        try:
            with pytest.raises(DatabaseRoleAuditError, match="required trigger"):
                audit_oz_membership_runtime(oz_membership_url)
        finally:
            with owner_engine.begin() as connection:
                connection.exec_driver_sql(
                    "DROP TRIGGER trg_oz_membership_validate_geometry_lineage "
                    "ON geo.opportunity_zone_membership"
                )
                connection.exec_driver_sql(
                    "CREATE TRIGGER trg_oz_membership_validate_geometry_lineage "
                    "BEFORE INSERT OR UPDATE ON geo.opportunity_zone_membership FOR EACH ROW "
                    "EXECUTE FUNCTION geo.validate_oz_membership_geometry_lineage()"
                )

        with owner_engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP TRIGGER trg_oz_membership_validate_geometry_lineage "
                "ON geo.opportunity_zone_membership"
            )
            connection.exec_driver_sql(
                "CREATE TRIGGER trg_oz_membership_validate_geometry_lineage "
                "BEFORE INSERT OR UPDATE ON geo.opportunity_zone_membership FOR EACH ROW "
                "WHEN (false) "
                "EXECUTE FUNCTION geo.validate_oz_membership_geometry_lineage()"
            )
        try:
            with pytest.raises(DatabaseRoleAuditError, match="required trigger"):
                audit_oz_membership_runtime(oz_membership_url)
        finally:
            with owner_engine.begin() as connection:
                connection.exec_driver_sql(
                    "DROP TRIGGER trg_oz_membership_validate_geometry_lineage "
                    "ON geo.opportunity_zone_membership"
                )
                connection.exec_driver_sql(
                    "CREATE TRIGGER trg_oz_membership_validate_geometry_lineage "
                    "BEFORE INSERT OR UPDATE ON geo.opportunity_zone_membership FOR EACH ROW "
                    "EXECUTE FUNCTION geo.validate_oz_membership_geometry_lineage()"
                )

        with owner_engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP TRIGGER trg_oz_membership_validate_geometry_lineage "
                "ON geo.opportunity_zone_membership"
            )
            connection.exec_driver_sql(
                """
                CREATE FUNCTION public.validate_oz_membership_geometry_lineage()
                RETURNS trigger
                LANGUAGE plpgsql
                SECURITY DEFINER
                SET search_path = pg_catalog
                AS $$
                BEGIN
                    RETURN NEW;
                END;
                $$
                """
            )
            connection.exec_driver_sql(
                "REVOKE ALL ON FUNCTION "
                "public.validate_oz_membership_geometry_lineage() FROM PUBLIC"
            )
            connection.exec_driver_sql(
                "CREATE TRIGGER trg_oz_membership_validate_geometry_lineage "
                "BEFORE INSERT OR UPDATE ON geo.opportunity_zone_membership FOR EACH ROW "
                "EXECUTE FUNCTION public.validate_oz_membership_geometry_lineage()"
            )
        try:
            with pytest.raises(DatabaseRoleAuditError, match="required trigger"):
                audit_oz_membership_runtime(oz_membership_url)
        finally:
            with owner_engine.begin() as connection:
                connection.exec_driver_sql(
                    "DROP TRIGGER trg_oz_membership_validate_geometry_lineage "
                    "ON geo.opportunity_zone_membership"
                )
                connection.exec_driver_sql(
                    "DROP FUNCTION public.validate_oz_membership_geometry_lineage()"
                )
                connection.exec_driver_sql(
                    "CREATE TRIGGER trg_oz_membership_validate_geometry_lineage "
                    "BEFORE INSERT OR UPDATE ON geo.opportunity_zone_membership FOR EACH ROW "
                    "EXECUTE FUNCTION geo.validate_oz_membership_geometry_lineage()"
                )

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
        _assert_privilege_denied(api_engine, "SELECT geometry FROM geo.parcel_geometry LIMIT 1")

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
        fabricated_payload = {
            **observation.model_dump(mode="json"),
            "source_id": "fabricated_source",
        }
        _assert_database_rejected(
            ingestion_engine,
            """
            INSERT INTO observation.parcel_observation (
                id, source_id, source_record_id, artifact_id, artifact_sha256,
                parser_version, payload, observed_at
            ) VALUES (
                :id, 'fabricated_source', :source_record_id, :artifact_id, :artifact_sha256,
                :parser_version, CAST(:payload AS jsonb), :observed_at
            )
            """,
            parameters={
                "id": uuid4(),
                "source_record_id": str(uuid4()),
                "artifact_id": artifact.id,
                "artifact_sha256": artifact.sha256,
                "parser_version": observation.parser_version,
                "payload": json.dumps(fabricated_payload),
                "observed_at": observation.observed_at,
            },
            sqlstates=frozenset({"23503", "P0001"}),
        )
        parcel_id = canonical_parcel_id(observation.jurisdiction_id, observation.local_parcel_id)
        with ingestion_engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO identity.parcel (
                        id, jurisdiction_id, local_parcel_id, created_at
                    ) VALUES (:id, :jurisdiction_id, :local_parcel_id, :created_at)
                    """
                ),
                {
                    "id": parcel_id,
                    "jurisdiction_id": observation.jurisdiction_id,
                    "local_parcel_id": observation.local_parcel_id,
                    "created_at": observation.observed_at,
                },
            )
        _assert_database_rejected(
            ingestion_engine,
            """
            INSERT INTO geo.parcel_geometry (
                observation_id, parcel_id, jurisdiction_id, local_parcel_id,
                source_id, source_record_id, source_artifact_id,
                source_artifact_sha256, parser_version, source_srid, geometry,
                geometry_was_repaired, geometry_repair_method, observed_at
            ) VALUES (
                :observation_id, :parcel_id, :jurisdiction_id, :local_parcel_id,
                :source_id, :source_record_id, :artifact_id,
                :artifact_sha256, :parser_version, 4326,
                ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromText(
                    'POLYGON((0 0,0 0.0001,0.0001 0.0001,0.0001 0,0 0))'
                ), 4326), 3857)), false, NULL, :fabricated_observed_at
            )
            """,
            parameters={
                "observation_id": observation.id,
                "parcel_id": parcel_id,
                "jurisdiction_id": observation.jurisdiction_id,
                "local_parcel_id": observation.local_parcel_id,
                "source_id": observation.source_id,
                "source_record_id": observation.source_record_id,
                "artifact_id": observation.artifact_id,
                "artifact_sha256": observation.artifact_sha256,
                "parser_version": observation.parser_version,
                "fabricated_observed_at": datetime(2030, 1, 1, tzinfo=UTC),
            },
            sqlstates=frozenset({"23503"}),
        )
        with ingestion_engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO geo.parcel_geometry (
                        observation_id, parcel_id, jurisdiction_id, local_parcel_id,
                        source_id, source_record_id, source_artifact_id,
                        source_artifact_sha256, parser_version, source_srid, geometry,
                        geometry_was_repaired, geometry_repair_method, observed_at
                    ) VALUES (
                        :observation_id, :parcel_id, :jurisdiction_id, :local_parcel_id,
                        :source_id, :source_record_id, :artifact_id,
                        :artifact_sha256, :parser_version, 4326,
                        ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromText(
                            'POLYGON((0 0,0 0.0001,0.0001 0.0001,0.0001 0,0 0))'
                        ), 4326), 3857)), false, NULL, :observed_at
                    )
                    """
                ),
                {
                    "observation_id": observation.id,
                    "parcel_id": parcel_id,
                    "jurisdiction_id": observation.jurisdiction_id,
                    "local_parcel_id": observation.local_parcel_id,
                    "source_id": observation.source_id,
                    "source_record_id": observation.source_record_id,
                    "artifact_id": observation.artifact_id,
                    "artifact_sha256": observation.artifact_sha256,
                    "parser_version": observation.parser_version,
                    "observed_at": observation.observed_at,
                },
            )
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

        import_run = OpportunityZoneImportRun(
            id=uuid4(),
            source_id="role_contract_oz_import",
            status=OpportunityZoneImportStatus.RUNNING,
            activation_id="role-contract-test",
            started_at=now,
            expected_tracts=1,
        )
        importer = PostgresOpportunityZoneRepository(oz_importer_engine)
        importer.save_run(import_run)
        importer.save_run(
            import_run.model_copy(
                update={
                    "status": OpportunityZoneImportStatus.FAILED,
                    "completed_at": now,
                    "error_code": "role_contract_test",
                }
            )
        )
        _assert_database_rejected(
            oz_importer_engine,
            "UPDATE geo.opportunity_zone_import_run "
            "SET error_detail = 'tampered terminal receipt' WHERE id = :id",
            parameters={"id": import_run.id},
            sqlstates=frozenset({"P0001"}),
        )

        round_id = f"role-contract-{uuid4()}"
        with owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO geo.opportunity_zone_round (
                        id, round_code, census_vintage, certification_status,
                        designation_status, effective_from, effective_to,
                        tract_intervals_vary, source_id, source_artifact_id,
                        source_artifact_sha256, authority_uri, loaded_at
                    ) VALUES (
                        :id, '2018', 2010, 'treasury_certified', 'effective',
                        :effective_from, :effective_to, false, :source_id,
                        :artifact_id, :artifact_sha256, 'https://example.invalid', :loaded_at
                    )
                    """
                ),
                {
                    "id": round_id,
                    "effective_from": date(2018, 1, 1),
                    "effective_to": date(2028, 12, 31),
                    "source_id": artifact.source_id,
                    "artifact_id": artifact.id,
                    "artifact_sha256": artifact.sha256,
                    "loaded_at": now,
                },
            )
        snapshot_id = uuid4()
        with oz_membership_engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO geo.opportunity_zone_membership_snapshot (
                        id, parcel_source_id, cohort_run_id, round_id, algorithm_version,
                        activation_id, effective_on, created_at, expected_parcels,
                        evaluated_parcels, inside_count, outside_count, boundary_review_count
                    ) VALUES (
                        :id, :parcel_source_id, :cohort_run_id, :round_id, 'role-test-v1',
                        'role-test-activation', :effective_on, :created_at, 1, 1, 0, 0, 1
                    )
                    """
                ),
                {
                    "id": snapshot_id,
                    "parcel_source_id": run.source_id,
                    "cohort_run_id": run.id,
                    "round_id": round_id,
                    "effective_on": now.date(),
                    "created_at": now,
                },
            )
        _assert_database_rejected(
            oz_membership_engine,
            """
            INSERT INTO geo.opportunity_zone_membership (
                membership_snapshot_id, round_id, parcel_id,
                parcel_geometry_observation_id, classification, tract_geoid,
                intersecting_tract_geoids, parcel_geometry_was_repaired,
                parcel_geometry_repair_method, designation_geometry_was_repaired,
                designation_geometry_repair_method, classified_at
            ) VALUES (
                :snapshot_id, :round_id, :parcel_id, :observation_id,
                'boundary_review', NULL, ARRAY[]::varchar(11)[], true,
                'fabricated-repair-method', false, NULL, :classified_at
            )
            """,
            parameters={
                "snapshot_id": snapshot_id,
                "round_id": round_id,
                "parcel_id": parcel_id,
                "observation_id": observation.id,
                "classified_at": now,
            },
            sqlstates=frozenset({"P0001"}),
        )
        build_id = uuid4()
        with oz_membership_engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO geo.opportunity_zone_membership_build_run (
                        id, parcel_source_id, cohort_run_id, round_id, algorithm_version,
                        activation_id, effective_on, status, started_at, expected_parcels
                    ) VALUES (
                        :id, :parcel_source_id, :cohort_run_id, :round_id, 'role-test-v1',
                        'role-test-activation', :effective_on, 'running', :started_at, 1
                    )
                    """
                ),
                {
                    "id": build_id,
                    "parcel_source_id": run.source_id,
                    "cohort_run_id": run.id,
                    "round_id": round_id,
                    "effective_on": now.date(),
                    "started_at": now,
                },
            )
            connection.execute(
                sa.text(
                    """
                    UPDATE geo.opportunity_zone_membership_build_run
                    SET status = 'failed', completed_at = :completed_at,
                        error_code = 'role_contract_test'
                    WHERE id = :id
                    """
                ),
                {"id": build_id, "completed_at": now},
            )
        _assert_database_rejected(
            oz_membership_engine,
            "UPDATE geo.opportunity_zone_membership_build_run "
            "SET error_detail = 'tampered terminal receipt' WHERE id = :id",
            parameters={"id": build_id},
            sqlstates=frozenset({"P0001"}),
        )
        _assert_privilege_denied(
            oz_importer_engine,
            "INSERT INTO geo.opportunity_zone_membership_build_run DEFAULT VALUES",
        )
        _assert_privilege_denied(
            oz_membership_engine,
            "INSERT INTO raw.artifact DEFAULT VALUES",
        )
        with owner_engine.begin() as connection:
            connection.execute(
                sa.text("DELETE FROM geo.opportunity_zone_membership_build_run WHERE id = :id"),
                {"id": build_id},
            )
            connection.execute(
                sa.text("DELETE FROM geo.opportunity_zone_membership_snapshot WHERE id = :id"),
                {"id": snapshot_id},
            )
            connection.execute(
                sa.text("DELETE FROM geo.opportunity_zone_round WHERE id = :id"),
                {"id": round_id},
            )
            connection.execute(
                sa.text("DELETE FROM geo.opportunity_zone_import_run WHERE id = :id"),
                {"id": import_run.id},
            )
    finally:
        oz_membership_engine.dispose()
        oz_importer_engine.dispose()
        api_engine.dispose()
        ingestion_engine.dispose()
        owner_engine.dispose()
