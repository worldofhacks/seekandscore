"""Parcel geometry, membership lifecycle, and coordinate-free API evidence tests."""

import hashlib
import json
import os
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from pydantic import ValidationError

from seekandscore.acquisition.models import (
    NormalizedParcelObservation,
    RawArtifact,
    SourceRun,
    SourceRunProfile,
    SourceRunStatus,
)
from seekandscore.acquisition.repository import PostgresAcquisitionRepository
from seekandscore.bootstrap import oz_private_display_is_approved
from seekandscore.db.migrate import build_config
from seekandscore.geography.opportunity_zones.membership import (
    OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
    OpportunityZoneMembershipError,
    OpportunityZoneMembershipService,
    PostgresOpportunityZoneMembershipRepository,
)
from seekandscore.geography.opportunity_zones.models import (
    DesignationStatus,
    OpportunityZoneClassification,
    OpportunityZoneDesignationEvidence,
    OpportunityZoneEvidence,
    OpportunityZoneEvidenceReason,
    OpportunityZoneImportRun,
    OpportunityZoneImportStatus,
    OpportunityZoneMembershipRecord,
    OpportunityZoneRound,
    OpportunityZoneSnapshot,
    ParcelGeometryEvidence,
)
from seekandscore.geography.opportunity_zones.repository import PostgresOpportunityZoneRepository
from seekandscore.geography.opportunity_zones.source import (
    CDFI_QOZ_2018_ACTIVATION_ID,
    CDFI_QOZ_2018_PRIVATE_DISPLAY_APPROVAL_ID,
    CDFI_QOZ_2018_ROUND_ID,
    CDFI_QOZ_2018_SOURCE,
)
from seekandscore.identity import canonical_parcel_id
from seekandscore.platform.settings import Settings
from seekandscore.readmodels import LiveCandidateRepository
from seekandscore.registry import InMemorySourceRegistry
from seekandscore.registry.sources import TRAVIS_TCAD_DISPLAY_APPROVAL_ID
from test_live_candidates import NOW, seeded_repository
from test_opportunity_zones import FIXTURE, adapter_for, build_archive


class StaticOpportunityZoneEvidence:
    def get_snapshot(
        self,
        *,
        cohort_run_id: UUID,
        parcel_ids: tuple[UUID, ...],
    ) -> OpportunityZoneSnapshot:
        evidence = OpportunityZoneEvidence(
            classification=OpportunityZoneClassification.INSIDE,
            reason_code=OpportunityZoneEvidenceReason.MATCHED_DESIGNATED_TRACT,
            method="postgis_strict_interior_v1",
            classified_at=NOW,
            parcel_geometry=ParcelGeometryEvidence(
                source_id="travis_tcad_parcels",
                source_record_id="101",
                artifact_sha256="a" * 64,
                observed_at=NOW,
                geometry_repaired=False,
            ),
            designation=OpportunityZoneDesignationEvidence(
                round_id="us-federal-qoz-2018",
                tract_geoid="48453001857",
                intersecting_tract_geoids=("48453001857",),
                census_vintage=2010,
                designation_status="effective",
                effective_from=date(2018, 1, 1),
                effective_to=date(2028, 12, 31),
                source_id="federal_qoz_2018_designations",
                source_artifact_sha256="b" * 64,
                authority_uri="https://www.cdfifund.gov/opportunity-zones",
            ),
        )
        return OpportunityZoneSnapshot(
            cohort_run_id=cohort_run_id,
            complete=True,
            memberships=tuple(
                OpportunityZoneMembershipRecord(parcel_id=parcel_id, evidence=evidence)
                for parcel_id in parcel_ids
            ),
        )


def test_live_projection_serializes_inside_membership_with_lineage_but_no_coordinates() -> None:
    repository = LiveCandidateRepository(
        seeded_repository(),
        InMemorySourceRegistry(),
        display_enabled=True,
        opportunity_zones=StaticOpportunityZoneEvidence(),
    )

    candidate = repository.list(limit=25, cursor=None, dataset_mode="live").items[0]
    payload = candidate.model_dump(mode="json")

    assert candidate.opportunity_zone_status == "effective"
    assert payload["opportunity_zone_evidence"]["classification"] == "inside"
    assert payload["opportunity_zone_evidence"]["designation"]["tract_geoid"] == "48453001857"
    assert payload["evidence"] == {
        "source_count": 2,
        "unresolved_conflict_count": 0,
        "freshness": "current",
    }
    assert "coordinates" not in candidate.model_dump_json().lower()


def test_private_oz_display_requires_both_exact_gates_and_approved_parcel_display() -> None:
    with pytest.raises(ValidationError, match="approved OZ_2018_PRIVATE_DISPLAY_APPROVAL_ID"):
        Settings(oz_2018_private_display_enabled=True)
    with pytest.raises(ValidationError, match="requires approved parcel display"):
        Settings(
            oz_2018_private_display_enabled=True,
            oz_2018_private_display_approval_id=CDFI_QOZ_2018_PRIVATE_DISPLAY_APPROVAL_ID,
        )

    settings = Settings(
        live_source_display_enabled=True,
        live_source_display_approval_id=TRAVIS_TCAD_DISPLAY_APPROVAL_ID,
        oz_2018_private_display_enabled=True,
        oz_2018_private_display_approval_id=CDFI_QOZ_2018_PRIVATE_DISPLAY_APPROVAL_ID,
    )
    assert settings.oz_2018_private_display_enabled is True
    assert oz_private_display_is_approved(settings) is True

    descriptor_denied = CDFI_QOZ_2018_SOURCE.model_copy(update={"display_allowed": False})
    assert oz_private_display_is_approved(settings, descriptor_denied) is False
    assert oz_private_display_is_approved(Settings(), CDFI_QOZ_2018_SOURCE) is False


def test_membership_builder_rejects_newer_incomplete_cohort_attempt() -> None:
    acquisition = seeded_repository()
    complete = acquisition.latest_complete_run(
        "travis_tcad_parcels", run_profile=SourceRunProfile.COHORT
    )
    assert complete is not None
    acquisition.save_run(
        complete.model_copy(
            update={
                "id": UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
                "status": SourceRunStatus.FAILED,
                "started_at": NOW + timedelta(minutes=1),
                "completed_at": NOW + timedelta(minutes=1),
                "artifact_ids": (),
                "error_code": "fixture",
            }
        )
    )
    memberships = MagicMock()
    service = OpportunityZoneMembershipService(
        acquisition=acquisition,
        memberships=memberships,
    )

    with pytest.raises(OpportunityZoneMembershipError, match="latest TCAD cohort attempt"):
        service.build(
            build_enabled=True,
            activation_id=OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
        )
    memberships.build_snapshot.assert_not_called()


def test_candidate_snapshot_selects_only_the_complete_run_parser_version() -> None:
    acquisition = seeded_repository()
    original = next(iter(acquisition.observations.values()))
    current = acquisition.latest_complete_run(
        "travis_tcad_parcels", run_profile=SourceRunProfile.COHORT
    )
    assert current is not None
    geometry_parser = "travis-tcad-parcel-geometry-v2"
    acquisition.save_observations(
        (
            original.model_copy(
                update={
                    "id": UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
                    "parser_version": geometry_parser,
                    "situs_address": "CURRENT GEOMETRY PARSER",
                }
            ),
        )
    )
    acquisition.save_run(current.model_copy(update={"parser_version": geometry_parser}))

    page = LiveCandidateRepository(
        acquisition,
        InMemorySourceRegistry(),
        display_enabled=True,
    ).list(limit=25, cursor=None, dataset_mode="live")

    assert page.items[0].id == canonical_parcel_id("us-tx-travis", "700001")
    assert page.items[0].display_name == "CURRENT GEOMETRY PARSER"


TEST_DATABASE_URL = os.getenv("SEEKANDSCORE_TEST_DATABASE_URL")


def _parcel_geometry(coordinates: list[list[float]]) -> str:
    return json.dumps({"type": "MultiPolygon", "coordinates": [[coordinates]]})


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="SEEKANDSCORE_TEST_DATABASE_URL is not set")
def test_postgis_membership_is_complete_replay_safe_and_geometry_atomic() -> None:
    assert TEST_DATABASE_URL is not None
    database_name = sa.engine.make_url(TEST_DATABASE_URL).database or ""
    if not database_name.endswith("_test"):
        pytest.fail("SEEKANDSCORE_TEST_DATABASE_URL must name a database ending in _test")
    command.upgrade(build_config(TEST_DATABASE_URL), "head")
    engine = sa.create_engine(TEST_DATABASE_URL)
    acquisition = PostgresAcquisitionRepository(engine)
    zone_repository = PostgresOpportunityZoneRepository(engine)
    now = datetime.now(UTC)
    tract_records = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tract_records[1]["rings"] = [[[200, 200], [300, 300], [200, 300], [300, 200], [200, 200]]]
    archive = build_archive(tract_records)
    zone_sha = hashlib.sha256(archive).hexdigest()
    memberships = PostgresOpportunityZoneMembershipRepository(
        engine,
        expected_tracts=2,
        expected_designation_sha256=zone_sha,
        expected_designation_repairs=1,
    )
    zone_artifact = RawArtifact(
        id=UUID("11111111-aaaa-4111-8111-111111111111"),
        source_id=CDFI_QOZ_2018_SOURCE.id,
        sha256=zone_sha,
        byte_count=len(archive),
        media_type="application/zip",
        storage_uri=f"s3://private-test/{zone_sha}.zip",
        original_uri=CDFI_QOZ_2018_SOURCE.original_uri,
        request_params={},
        retrieved_at=now,
    )
    round_record = OpportunityZoneRound(
        id=CDFI_QOZ_2018_ROUND_ID,
        round_code="2018",
        census_vintage=2010,
        certification_status=DesignationStatus.TREASURY_CERTIFIED,
        designation_status=DesignationStatus.EFFECTIVE,
        effective_from=date(2017, 12, 22),
        effective_to=date(2028, 12, 31),
        tract_intervals_vary=True,
        source_id=CDFI_QOZ_2018_SOURCE.id,
        source_artifact_id=zone_artifact.id,
        source_artifact_sha256=zone_sha,
        authority_uri=CDFI_QOZ_2018_SOURCE.terms_uri,
    )
    parcel_artifact = RawArtifact(
        id=UUID("22222222-aaaa-4222-8222-222222222222"),
        source_id="travis_tcad_parcels",
        sha256="c" * 64,
        byte_count=2,
        media_type="application/json",
        storage_uri="s3://private-test/parcels.json",
        original_uri="https://example.invalid/query",
        request_params={},
        retrieved_at=now,
    )
    geometry_parser = "travis-tcad-parcel-geometry-v2"
    geometries = (
        _parcel_geometry(
            [
                [0.0001, 0.0001],
                [0.0002, 0.0001],
                [0.0002, 0.0002],
                [0.0001, 0.0002],
                [0.0001, 0.0001],
            ]
        ),
        _parcel_geometry(
            [[0.01, 0.01], [0.011, 0.01], [0.011, 0.011], [0.01, 0.011], [0.01, 0.01]]
        ),
        _parcel_geometry(
            [[0.0008, 0.0001], [0.001, 0.0001], [0.001, 0.0002], [0.0008, 0.0002], [0.0008, 0.0001]]
        ),
        _parcel_geometry(
            [
                [0.02, 0.02],
                [0.021, 0.021],
                [0.02, 0.021],
                [0.021, 0.02],
                [0.02, 0.02],
            ]
        ),
        _parcel_geometry(
            [
                [0.00195, 0.00188],
                [0.00205, 0.00188],
                [0.00205, 0.00193],
                [0.00195, 0.00193],
                [0.00195, 0.00188],
            ]
        ),
    )
    observations = tuple(
        NormalizedParcelObservation(
            id=UUID(f"33333333-aaaa-4333-8333-{index:012d}"),
            source_id="travis_tcad_parcels",
            source_record_id=str(index),
            artifact_id=parcel_artifact.id,
            artifact_sha256=parcel_artifact.sha256,
            parser_version=geometry_parser,
            jurisdiction_id="us-tx-travis",
            local_parcel_id=str(9_000_000 + index),
            geographic_id=None,
            situs_address=f"{index} TEST RD",
            situs_city="DEL VALLE",
            situs_zip="78617",
            tcad_acres=2,
            geometry_srid=4326,
            geometry_geojson=geometry,
            observed_at=now,
        )
        for index, geometry in enumerate(geometries, start=1)
    )
    cohort = SourceRun(
        id=UUID("44444444-aaaa-4444-8444-444444444444"),
        source_id="travis_tcad_parcels",
        status=SourceRunStatus.SUCCEEDED,
        requested_at=now,
        started_at=now,
        completed_at=now,
        retrieved_at=now,
        records_fetched=5,
        observations_created=5,
        artifact_ids=(parcel_artifact.id,),
        adapter_version="travis-tcad-arcgis-v1",
        parser_version=geometry_parser,
        run_profile=SourceRunProfile.COHORT,
        configuration_hash="d" * 64,
        activation_id="test-only",
    )
    initial_import_id = UUID("66666666-aaaa-4666-8666-666666666661")
    replay_import_id = UUID("66666666-aaaa-4666-8666-666666666662")
    legacy_observation = observations[0].model_copy(
        update={
            "id": UUID("77777777-aaaa-4777-8777-777777777777"),
            "parser_version": "travis-tcad-parser-v1",
            "geometry_srid": None,
            "geometry_geojson": None,
        }
    )
    try:
        zone_repository.register_source(CDFI_QOZ_2018_SOURCE, registered_at=now)
        zone_repository.save_artifact(zone_artifact)
        with adapter_for(archive).open_archive(archive, artifact_id=zone_artifact.id) as dataset:
            zone_repository.import_tracts(
                round_record=round_record,
                tracts=dataset.iter_tracts(),
                expected_tracts=2,
                expected_geometry_repairs=1,
                loaded_at=now,
            )
        acquisition.save_artifact(parcel_artifact)
        assert acquisition.save_observations(observations) == 5
        assert acquisition.save_observations((legacy_observation,)) == 1
        acquisition.save_run(cohort)
        with engine.connect() as connection:
            payloads = connection.scalars(
                sa.text(
                    "SELECT payload FROM observation.parcel_observation "
                    "WHERE artifact_id = :artifact_id"
                ),
                {"artifact_id": parcel_artifact.id},
            ).all()
        serialized_payloads = json.dumps(payloads).lower()
        assert "geometry_geojson" not in serialized_payloads
        assert "geometry_srid" not in serialized_payloads
        assert "coordinates" not in serialized_payloads

        initial_import = OpportunityZoneImportRun(
            id=initial_import_id,
            source_id=CDFI_QOZ_2018_SOURCE.id,
            status=OpportunityZoneImportStatus.RUNNING,
            activation_id=CDFI_QOZ_2018_ACTIVATION_ID,
            started_at=now - timedelta(minutes=2),
            expected_tracts=2,
        )
        zone_repository.save_run(initial_import)
        zone_repository.save_run(
            initial_import.model_copy(
                update={
                    "status": OpportunityZoneImportStatus.SUCCEEDED,
                    "completed_at": now - timedelta(minutes=2),
                    "source_artifact_id": zone_artifact.id,
                    "source_artifact_sha256": zone_sha,
                    "imported_tracts": 2,
                }
            )
        )

        with pytest.raises(OpportunityZoneMembershipError, match="unchanged static QOZ import"):
            memberships.build_snapshot(
                cohort=cohort,
                activation_id=OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
                expected_parcels=5,
                expected_tracts=2,
            )

        replay_import = initial_import.model_copy(
            update={
                "id": replay_import_id,
                "started_at": now - timedelta(minutes=1),
            }
        )
        zone_repository.save_run(replay_import)
        zone_repository.save_run(
            replay_import.model_copy(
                update={
                    "status": OpportunityZoneImportStatus.SUCCEEDED_UNCHANGED,
                    "completed_at": now - timedelta(minutes=1),
                    "source_artifact_id": zone_artifact.id,
                    "source_artifact_sha256": zone_sha,
                    "imported_tracts": 2,
                }
            )
        )

        wrong_sha_memberships = PostgresOpportunityZoneMembershipRepository(
            engine,
            expected_tracts=2,
            expected_designation_sha256="f" * 64,
            expected_designation_repairs=1,
        )
        with pytest.raises(OpportunityZoneMembershipError, match="unchanged static QOZ import"):
            wrong_sha_memberships.build_snapshot(
                cohort=cohort,
                activation_id=OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
                expected_parcels=5,
                expected_tracts=2,
            )
        wrong_repair_memberships = PostgresOpportunityZoneMembershipRepository(
            engine,
            expected_tracts=2,
            expected_designation_sha256=zone_sha,
            expected_designation_repairs=0,
        )
        with pytest.raises(OpportunityZoneMembershipError, match="complete effective layer"):
            wrong_repair_memberships.build_snapshot(
                cohort=cohort,
                activation_id=OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
                expected_parcels=5,
                expected_tracts=2,
            )

        first = memberships.build_snapshot(
            cohort=cohort,
            activation_id=OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
            expected_parcels=5,
            expected_tracts=2,
        )
        before_replay = memberships.get_snapshot(
            cohort_run_id=cohort.id,
            parcel_ids=tuple(
                canonical_parcel_id(item.jurisdiction_id, item.local_parcel_id)
                for item in observations
            ),
        )
        assert before_replay.complete is False
        with pytest.raises(OpportunityZoneMembershipError, match="unchanged build replay"):
            memberships.verify_snapshot(cohort=cohort, expected_parcels=5)

        replay = memberships.build_snapshot(
            cohort=cohort,
            activation_id=OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
            expected_parcels=5,
            expected_tracts=2,
        )

        assert (first.inside_count, first.outside_count, first.boundary_review_count) == (1, 1, 3)
        assert replay.status == "succeeded_unchanged"
        assert replay.snapshot_id == first.snapshot_id
        snapshot = memberships.get_snapshot(
            cohort_run_id=cohort.id,
            parcel_ids=tuple(
                canonical_parcel_id(item.jurisdiction_id, item.local_parcel_id)
                for item in observations
            ),
        )
        assert snapshot.complete is True
        repaired = next(
            item
            for item in snapshot.memberships
            if item.evidence.reason_code == "parcel_geometry_repaired"
        )
        assert repaired.evidence.classification == "boundary_review"
        assert repaired.evidence.designation is not None
        assert repaired.evidence.designation.intersecting_tract_geoids == ()
        designation_repaired = next(
            item
            for item in snapshot.memberships
            if item.evidence.reason_code == "designation_geometry_repaired"
        )
        assert designation_repaired.evidence.classification == "boundary_review"
        assert designation_repaired.evidence.designation is not None
        assert designation_repaired.evidence.designation.geometry_repaired is True
        assert designation_repaired.evidence.designation.repair_method == (
            "postgis_st_makevalid_collection_extract_v1"
        )

        with engine.begin() as connection:
            drifted = connection.execute(
                sa.text(
                    """
                    UPDATE registry.source_run
                    SET payload = jsonb_set(
                        jsonb_set(
                            payload,
                            '{artifact_ids}',
                            CAST(:artifact_ids AS jsonb),
                            false
                        ),
                        '{parser_version}',
                        to_jsonb(CAST(:parser_version AS text)),
                        false
                    )
                    WHERE id = :cohort_run_id
                    """
                ),
                {
                    "artifact_ids": json.dumps([str(uuid4())]),
                    "parser_version": "tampered-parser-v99",
                    "cohort_run_id": cohort.id,
                },
            )
            assert drifted.rowcount == 1
        drifted_snapshot = memberships.get_snapshot(
            cohort_run_id=cohort.id,
            parcel_ids=tuple(
                canonical_parcel_id(item.jurisdiction_id, item.local_parcel_id)
                for item in observations
            ),
        )
        assert drifted_snapshot.complete is False
        with pytest.raises(OpportunityZoneMembershipError, match="cohort artifact/parser lineage"):
            memberships.verify_snapshot(cohort=cohort, expected_parcels=5)
        with engine.begin() as connection:
            restored_lineage = connection.execute(
                sa.text(
                    """
                    UPDATE registry.source_run
                    SET payload = jsonb_set(
                        jsonb_set(
                            payload,
                            '{artifact_ids}',
                            CAST(:artifact_ids AS jsonb),
                            false
                        ),
                        '{parser_version}',
                        to_jsonb(CAST(:parser_version AS text)),
                        false
                    )
                    WHERE id = :cohort_run_id
                    """
                ),
                {
                    "artifact_ids": json.dumps([str(item) for item in cohort.artifact_ids]),
                    "parser_version": cohort.parser_version,
                    "cohort_run_id": cohort.id,
                },
            )
            assert restored_lineage.rowcount == 1

        inside_membership = next(
            item
            for item in snapshot.memberships
            if item.evidence.classification is OpportunityZoneClassification.INSIDE
        )
        outside_membership = next(
            item
            for item in snapshot.memberships
            if item.evidence.classification is OpportunityZoneClassification.OUTSIDE
        )
        assert inside_membership.evidence.designation is not None
        inside_tract_geoid = inside_membership.evidence.designation.tract_geoid
        assert inside_tract_geoid is not None
        with engine.begin() as connection:
            equal_count_tamper = connection.execute(
                sa.text(
                    """
                    UPDATE geo.opportunity_zone_membership
                    SET classification = CASE
                            WHEN parcel_id = :inside_parcel_id THEN 'outside'
                            ELSE 'inside'
                        END,
                        tract_geoid = CASE
                            WHEN parcel_id = :inside_parcel_id THEN NULL
                            ELSE :tract_geoid
                        END,
                        intersecting_tract_geoids = CASE
                            WHEN parcel_id = :inside_parcel_id
                                THEN ARRAY[]::varchar(11)[]
                            ELSE ARRAY[:tract_geoid]::varchar(11)[]
                        END
                    WHERE membership_snapshot_id = :snapshot_id
                      AND parcel_id IN (:inside_parcel_id, :outside_parcel_id)
                    """
                ),
                {
                    "snapshot_id": first.snapshot_id,
                    "inside_parcel_id": inside_membership.parcel_id,
                    "outside_parcel_id": outside_membership.parcel_id,
                    "tract_geoid": inside_tract_geoid,
                },
            )
            assert equal_count_tamper.rowcount == 2
        with pytest.raises(
            OpportunityZoneMembershipError,
            match="deterministic spatial replay",
        ):
            memberships.build_snapshot(
                cohort=cohort,
                activation_id=OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
                expected_parcels=5,
                expected_tracts=2,
            )
        with engine.begin() as connection:
            restored_semantics = connection.execute(
                sa.text(
                    """
                    UPDATE geo.opportunity_zone_membership
                    SET classification = CASE
                            WHEN parcel_id = :inside_parcel_id THEN 'inside'
                            ELSE 'outside'
                        END,
                        tract_geoid = CASE
                            WHEN parcel_id = :inside_parcel_id THEN :tract_geoid
                            ELSE NULL
                        END,
                        intersecting_tract_geoids = CASE
                            WHEN parcel_id = :inside_parcel_id
                                THEN ARRAY[:tract_geoid]::varchar(11)[]
                            ELSE ARRAY[]::varchar(11)[]
                        END
                    WHERE membership_snapshot_id = :snapshot_id
                      AND parcel_id IN (:inside_parcel_id, :outside_parcel_id)
                    """
                ),
                {
                    "snapshot_id": first.snapshot_id,
                    "inside_parcel_id": inside_membership.parcel_id,
                    "outside_parcel_id": outside_membership.parcel_id,
                    "tract_geoid": inside_tract_geoid,
                },
            )
            assert restored_semantics.rowcount == 2
        restored_replay = memberships.build_snapshot(
            cohort=cohort,
            activation_id=OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
            expected_parcels=5,
            expected_tracts=2,
        )
        assert restored_replay.status == "succeeded_unchanged"

        tampered_parcel_id = canonical_parcel_id(
            observations[0].jurisdiction_id,
            observations[0].local_parcel_id,
        )
        with engine.begin() as connection:
            changed = connection.execute(
                sa.text(
                    """
                    UPDATE geo.opportunity_zone_membership
                    SET classification = 'boundary_review', tract_geoid = NULL
                    WHERE membership_snapshot_id = :snapshot_id
                      AND parcel_id = :parcel_id
                      AND classification = 'inside'
                    """
                ),
                {"snapshot_id": first.snapshot_id, "parcel_id": tampered_parcel_id},
            )
            assert changed.rowcount == 1
        tampered = memberships.get_snapshot(
            cohort_run_id=cohort.id,
            parcel_ids=tuple(
                canonical_parcel_id(item.jurisdiction_id, item.local_parcel_id)
                for item in observations
            ),
        )
        assert tampered.complete is False
        with engine.begin() as connection:
            restored = connection.execute(
                sa.text(
                    """
                    UPDATE geo.opportunity_zone_membership
                    SET classification = 'inside', tract_geoid = intersecting_tract_geoids[1]
                    WHERE membership_snapshot_id = :snapshot_id
                      AND parcel_id = :parcel_id
                      AND classification = 'boundary_review'
                    """
                ),
                {"snapshot_id": first.snapshot_id, "parcel_id": tampered_parcel_id},
            )
            assert restored.rowcount == 1

        def future_clock() -> datetime:
            # UTC is already 2028 while this deliberately non-UTC DB session is still 2027.
            return datetime(2028, 1, 1, 0, 30, tzinfo=UTC)

        non_utc_engine = sa.create_engine(
            TEST_DATABASE_URL,
            connect_args={"options": "-c timezone=Pacific/Honolulu"},
        )
        try:
            non_utc_memberships = PostgresOpportunityZoneMembershipRepository(
                non_utc_engine,
                expected_tracts=2,
                expected_designation_sha256=zone_sha,
                expected_designation_repairs=1,
            )
            future = non_utc_memberships.build_snapshot(
                cohort=cohort,
                activation_id=OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
                expected_parcels=5,
                expected_tracts=2,
                clock=future_clock,
            )
        finally:
            non_utc_engine.dispose()
        assert (
            future.inside_count,
            future.outside_count,
            future.boundary_review_count,
        ) == (1, 2, 2)
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM geo.opportunity_zone_membership_snapshot")
                )
                == 2
            )
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM geo.opportunity_zone_membership_build_run")
                )
                == 8
            )

        invalid = observations[0].model_copy(
            update={
                "id": UUID("55555555-aaaa-4555-8555-555555555555"),
                "source_record_id": "invalid",
                "local_parcel_id": "9999999",
                "geometry_geojson": json.dumps({"type": "MultiPolygon", "coordinates": [[]]}),
            }
        )
        with pytest.raises(sa.exc.DBAPIError):
            acquisition.save_observations((invalid,))
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM observation.parcel_observation WHERE id = :id"),
                    {"id": invalid.id},
                )
                == 0
            )
    finally:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "DELETE FROM geo.opportunity_zone_membership_build_run "
                    "WHERE cohort_run_id = :id"
                ),
                {"id": cohort.id},
            )
            connection.execute(
                sa.text("DELETE FROM geo.opportunity_zone_import_run WHERE id = ANY(:ids)"),
                {"ids": [initial_import_id, replay_import_id]},
            )
            connection.execute(
                sa.text(
                    "DELETE FROM geo.opportunity_zone_membership "
                    "WHERE membership_snapshot_id IN ("
                    "SELECT id FROM geo.opportunity_zone_membership_snapshot "
                    "WHERE cohort_run_id = :id)"
                ),
                {"id": cohort.id},
            )
            connection.execute(
                sa.text(
                    "DELETE FROM geo.opportunity_zone_membership_snapshot WHERE cohort_run_id = :id"
                ),
                {"id": cohort.id},
            )
            connection.execute(
                sa.text("DELETE FROM registry.source_run WHERE id = :id"), {"id": cohort.id}
            )
            connection.execute(
                sa.text("DELETE FROM geo.parcel_geometry WHERE observation_id = ANY(:ids)"),
                {"ids": [item.id for item in observations]},
            )
            connection.execute(
                sa.text("DELETE FROM observation.parcel_observation WHERE id = ANY(:ids)"),
                {"ids": [*(item.id for item in observations), legacy_observation.id]},
            )
            connection.execute(
                sa.text("DELETE FROM identity.parcel WHERE id = ANY(:ids)"),
                {
                    "ids": [
                        canonical_parcel_id(item.jurisdiction_id, item.local_parcel_id)
                        for item in observations
                    ]
                },
            )
            connection.execute(
                sa.text("DELETE FROM geo.opportunity_zone_tract WHERE round_id = :round_id"),
                {"round_id": CDFI_QOZ_2018_ROUND_ID},
            )
            connection.execute(
                sa.text("DELETE FROM geo.opportunity_zone_round WHERE id = :round_id"),
                {"round_id": CDFI_QOZ_2018_ROUND_ID},
            )
            connection.execute(
                sa.text("DELETE FROM raw.artifact WHERE id = ANY(:ids)"),
                {"ids": [zone_artifact.id, parcel_artifact.id]},
            )
            connection.execute(
                sa.text("DELETE FROM registry.source_definition WHERE id = :source_id"),
                {"source_id": CDFI_QOZ_2018_SOURCE.id},
            )
        engine.dispose()
