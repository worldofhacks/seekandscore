"""Versioned, replay-safe parcel membership against frozen official QOZ geography."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from seekandscore.acquisition.models import SourceRun, SourceRunProfile
from seekandscore.acquisition.repository import AcquisitionRepository
from seekandscore.geography.opportunity_zones.models import (
    OpportunityZoneClassification,
    OpportunityZoneDesignationEvidence,
    OpportunityZoneEvidence,
    OpportunityZoneEvidenceReason,
    OpportunityZoneMembershipBuildOutcome,
    OpportunityZoneMembershipBuildStatus,
    OpportunityZoneMembershipRecord,
    OpportunityZoneSnapshot,
    ParcelGeometryEvidence,
)
from seekandscore.geography.opportunity_zones.source import (
    CDFI_QOZ_2018_ACTIVATION_ID,
    CDFI_QOZ_2018_CENSUS_VINTAGE,
    CDFI_QOZ_2018_EXPECTED_GEOMETRY_REPAIRS,
    CDFI_QOZ_2018_EXPECTED_SHA256,
    CDFI_QOZ_2018_EXPECTED_TRACTS,
    CDFI_QOZ_2018_ROUND_ID,
    CDFI_QOZ_2018_SOURCE_ID,
)
from seekandscore.platform.errors import durable_error_detail

OZ_MEMBERSHIP_ALGORITHM_VERSION = "postgis_strict_interior_v1"
OZ_MEMBERSHIP_BUILD_ACTIVATION_ID = "GEO-TCAD-QOZ-2018-MEMBERSHIP-20260814-V1"
_SNAPSHOT_NAMESPACE = UUID("8a263f32-237f-45db-8724-c54fe80e44f3")


class OpportunityZoneMembershipError(RuntimeError):
    """A complete, lineage-safe membership snapshot could not be built or verified."""


class OpportunityZoneMembershipBuildDisabledError(PermissionError):
    """No spatial build occurs without its independent exact activation gates."""


class OpportunityZoneEvidenceRepository(Protocol):
    def get_snapshot(
        self,
        *,
        cohort_run_id: UUID,
        parcel_ids: tuple[UUID, ...],
    ) -> OpportunityZoneSnapshot: ...


class UnavailableOpportunityZoneEvidenceRepository:
    def __init__(self, reason: OpportunityZoneEvidenceReason) -> None:
        self.reason = reason

    def get_snapshot(
        self,
        *,
        cohort_run_id: UUID,
        parcel_ids: tuple[UUID, ...],
    ) -> OpportunityZoneSnapshot:
        del parcel_ids
        return OpportunityZoneSnapshot(
            cohort_run_id=cohort_run_id,
            complete=False,
            unavailable_reason=self.reason,
        )


class PostgresOpportunityZoneMembershipRepository:
    """Build immutable snapshots and read coordinate-free evidence projections."""

    def __init__(
        self,
        engine: Engine,
        *,
        expected_tracts: int = CDFI_QOZ_2018_EXPECTED_TRACTS,
        expected_designation_sha256: str = CDFI_QOZ_2018_EXPECTED_SHA256,
        expected_designation_repairs: int = CDFI_QOZ_2018_EXPECTED_GEOMETRY_REPAIRS,
    ) -> None:
        self.engine = engine
        self.expected_tracts = expected_tracts
        self.expected_designation_sha256 = expected_designation_sha256
        self.expected_designation_repairs = expected_designation_repairs

    def build_snapshot(
        self,
        *,
        cohort: SourceRun,
        activation_id: str,
        expected_parcels: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        expected_tracts: int = CDFI_QOZ_2018_EXPECTED_TRACTS,
    ) -> OpportunityZoneMembershipBuildOutcome:
        if activation_id != OZ_MEMBERSHIP_BUILD_ACTIVATION_ID:
            raise OpportunityZoneMembershipError(
                "membership build requires the exact reviewed activation ID"
            )
        if not cohort.is_complete_cohort:
            raise OpportunityZoneMembershipError("membership build requires a complete cohort")
        if cohort.records_fetched != expected_parcels:
            raise OpportunityZoneMembershipError(
                f"membership build requires exactly {expected_parcels} cohort records"
            )
        if expected_tracts != self.expected_tracts:
            raise OpportunityZoneMembershipError(
                "membership build tract expectation differs from the repository policy"
            )
        started_at = clock()
        effective_on = started_at.astimezone(UTC).date()
        build_id = uuid4()
        snapshot_id = uuid5(
            _SNAPSHOT_NAMESPACE,
            f"{cohort.id}:{CDFI_QOZ_2018_ROUND_ID}:"
            f"{OZ_MEMBERSHIP_ALGORITHM_VERSION}:{effective_on.isoformat()}",
        )
        self._insert_build_receipt(
            build_id=build_id,
            cohort=cohort,
            activation_id=activation_id,
            started_at=started_at,
            effective_on=effective_on,
            expected_parcels=expected_parcels,
        )
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    sa.text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"oz-membership:{cohort.id}:{CDFI_QOZ_2018_ROUND_ID}"},
                )
                self._require_verified_import_replay(
                    connection,
                    expected_tracts=expected_tracts,
                    effective_at=started_at,
                )
                self._stage_cohort(connection, cohort=cohort)
                cohort_count, missing_geometry = connection.execute(
                    sa.text(
                        "SELECT count(*), count(*) FILTER (WHERE geometry IS NULL) "
                        "FROM oz_parcel_stage"
                    )
                ).one()
                if int(cohort_count) != expected_parcels or int(missing_geometry) != 0:
                    raise OpportunityZoneMembershipError(
                        "membership build requires typed geometry for every cohort parcel"
                    )
                classified_at = clock()
                if classified_at.astimezone(UTC).date() != effective_on:
                    raise OpportunityZoneMembershipError(
                        "membership build crossed a UTC effective-date boundary"
                    )
                self._require_verified_import_replay(
                    connection,
                    expected_tracts=expected_tracts,
                    effective_at=classified_at,
                )
                self._classify(connection, classified_at=classified_at)
                self._validate_designation_repair_lineage(connection)
                counts = self._classification_counts(connection)
                if counts["evaluated_parcels"] != expected_parcels:
                    raise OpportunityZoneMembershipError(
                        "membership classifier did not evaluate the complete parcel cohort"
                    )
                existing = self._existing_snapshot(connection, snapshot_id=snapshot_id)
                if existing is not None:
                    self._require_snapshot_cohort_lineage(
                        connection,
                        snapshot_id=snapshot_id,
                    )
                    self._verify_snapshot_rows(
                        connection,
                        snapshot_id=snapshot_id,
                        expected_parcels=expected_parcels,
                        expected=existing,
                    )
                    self._verify_snapshot_replay_rows(
                        connection,
                        snapshot_id=snapshot_id,
                    )
                    completed_at = clock()
                    self._complete_build_receipt(
                        connection,
                        build_id=build_id,
                        snapshot_id=snapshot_id,
                        status=OpportunityZoneMembershipBuildStatus.SUCCEEDED_UNCHANGED,
                        counts=existing,
                        completed_at=completed_at,
                    )
                    return _outcome(
                        build_id=build_id,
                        cohort=cohort,
                        activation_id=activation_id,
                        snapshot_id=snapshot_id,
                        status=OpportunityZoneMembershipBuildStatus.SUCCEEDED_UNCHANGED,
                        counts=existing,
                        started_at=started_at,
                        completed_at=completed_at,
                    )
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO geo.opportunity_zone_membership_snapshot (
                            id, parcel_source_id, cohort_run_id, round_id, algorithm_version,
                            activation_id, effective_on, created_at,
                            expected_parcels, evaluated_parcels,
                            inside_count, outside_count, boundary_review_count
                        ) VALUES (
                            :id, :parcel_source_id, :cohort_run_id, :round_id, :algorithm_version,
                            :activation_id, :effective_on, :created_at,
                            :expected_parcels, :evaluated_parcels,
                            :inside_count, :outside_count, :boundary_review_count
                        )
                        """
                    ),
                    {
                        "id": snapshot_id,
                        "parcel_source_id": cohort.source_id,
                        "cohort_run_id": cohort.id,
                        "round_id": CDFI_QOZ_2018_ROUND_ID,
                        "algorithm_version": OZ_MEMBERSHIP_ALGORITHM_VERSION,
                        "activation_id": activation_id,
                        "effective_on": effective_on,
                        "created_at": classified_at,
                        "expected_parcels": expected_parcels,
                        **counts,
                    },
                )
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO geo.opportunity_zone_membership (
                            membership_snapshot_id, round_id, parcel_id,
                            parcel_geometry_observation_id, classification, tract_geoid,
                            intersecting_tract_geoids, parcel_geometry_was_repaired,
                            parcel_geometry_repair_method,
                            designation_geometry_was_repaired,
                            designation_geometry_repair_method, classified_at
                        )
                        SELECT :snapshot_id, :round_id, parcel_id, observation_id,
                               classification, tract_geoid, intersecting_tract_geoids,
                               parcel_geometry_was_repaired,
                               parcel_geometry_repair_method,
                               designation_geometry_was_repaired,
                               designation_geometry_repair_method, classified_at
                        FROM oz_membership_stage
                        """
                    ),
                    {"snapshot_id": snapshot_id, "round_id": CDFI_QOZ_2018_ROUND_ID},
                )
                inserted = int(
                    connection.scalar(
                        sa.text(
                            "SELECT count(*) FROM geo.opportunity_zone_membership "
                            "WHERE membership_snapshot_id = :snapshot_id"
                        ),
                        {"snapshot_id": snapshot_id},
                    )
                    or 0
                )
                if inserted != expected_parcels:
                    raise OpportunityZoneMembershipError(
                        "membership snapshot insert did not preserve the complete cohort"
                    )
                completed_at = clock()
                self._complete_build_receipt(
                    connection,
                    build_id=build_id,
                    snapshot_id=snapshot_id,
                    status=OpportunityZoneMembershipBuildStatus.SUCCEEDED,
                    counts=counts,
                    completed_at=completed_at,
                )
            return _outcome(
                build_id=build_id,
                cohort=cohort,
                activation_id=activation_id,
                snapshot_id=snapshot_id,
                status=OpportunityZoneMembershipBuildStatus.SUCCEEDED,
                counts=counts,
                started_at=started_at,
                completed_at=completed_at,
            )
        except (sa.exc.SQLAlchemyError, OpportunityZoneMembershipError) as error:
            self._fail_build_receipt(build_id=build_id, error=error, completed_at=clock())
            if isinstance(error, OpportunityZoneMembershipError):
                raise
            raise OpportunityZoneMembershipError("PostGIS membership build failed") from error

    def verify_snapshot(
        self,
        *,
        cohort: SourceRun,
        expected_parcels: int,
    ) -> OpportunityZoneMembershipBuildOutcome:
        with self.engine.connect() as connection:
            now = datetime.now(UTC)
            self._require_verified_import_replay(
                connection,
                expected_tracts=self.expected_tracts,
                effective_at=now,
            )
            snapshot_id = self._latest_applicable_snapshot_id(
                connection,
                cohort_run_id=cohort.id,
            )
            if snapshot_id is None:
                raise OpportunityZoneMembershipError(
                    "no currently applicable membership snapshot exists for the latest cohort"
                )
            counts = self._existing_snapshot(connection, snapshot_id=snapshot_id)
            if counts is None:
                raise OpportunityZoneMembershipError(
                    "no complete membership snapshot exists for the latest complete cohort"
                )
            self._require_snapshot_cohort_lineage(
                connection,
                snapshot_id=snapshot_id,
            )
            replay_receipt = self._require_replayed_build(
                connection,
                cohort_run_id=cohort.id,
                snapshot_id=snapshot_id,
                expected_parcels=expected_parcels,
            )
            self._verify_snapshot_rows(
                connection,
                snapshot_id=snapshot_id,
                expected_parcels=expected_parcels,
                expected=counts,
            )
        started_at = cast(datetime, replay_receipt["started_at"])
        completed_at = cast(datetime, replay_receipt["completed_at"])
        return _outcome(
            build_id=UUID(str(replay_receipt["id"])),
            cohort=cohort,
            activation_id=OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
            snapshot_id=snapshot_id,
            status=OpportunityZoneMembershipBuildStatus.SUCCEEDED_UNCHANGED,
            counts=counts,
            started_at=started_at,
            completed_at=completed_at,
        )

    def get_snapshot(
        self,
        *,
        cohort_run_id: UUID,
        parcel_ids: tuple[UUID, ...],
    ) -> OpportunityZoneSnapshot:
        if not parcel_ids:
            return OpportunityZoneSnapshot(cohort_run_id=cohort_run_id, complete=True)
        with self.engine.connect() as connection:
            snapshot = (
                connection.execute(
                    sa.text(
                        """
                        WITH latest_build AS (
                            SELECT *
                            FROM geo.opportunity_zone_membership_build_run
                            WHERE cohort_run_id = :cohort_run_id
                              AND round_id = :round_id
                              AND algorithm_version = :algorithm_version
                            ORDER BY started_at DESC, id DESC
                            LIMIT 1
                        )
                        SELECT s.id, s.round_id, s.evaluated_parcels
                        FROM latest_build AS b
                        JOIN geo.opportunity_zone_membership_snapshot AS s
                          ON s.id = b.snapshot_id
                         AND s.parcel_source_id = b.parcel_source_id
                         AND s.cohort_run_id = b.cohort_run_id
                         AND s.round_id = b.round_id
                         AND s.algorithm_version = b.algorithm_version
                         AND s.activation_id = b.activation_id
                         AND s.effective_on = b.effective_on
                         AND s.expected_parcels = b.expected_parcels
                         AND s.evaluated_parcels = b.evaluated_parcels
                         AND s.inside_count = b.inside_count
                         AND s.outside_count = b.outside_count
                         AND s.boundary_review_count = b.boundary_review_count
                        JOIN registry.source_run AS c
                          ON c.id = s.cohort_run_id
                         AND c.source_id = s.parcel_source_id
                        JOIN geo.opportunity_zone_round AS r ON r.id = s.round_id
                        JOIN LATERAL (
                            SELECT count(*) AS evaluated_parcels,
                                   count(*) FILTER (WHERE classification = 'inside')
                                       AS inside_count,
                                   count(*) FILTER (WHERE classification = 'outside')
                                       AS outside_count,
                                   count(*) FILTER (WHERE classification = 'boundary_review')
                                       AS boundary_review_count
                            FROM geo.opportunity_zone_membership AS actual_membership
                            WHERE actual_membership.membership_snapshot_id = s.id
                        ) AS actual ON actual.evaluated_parcels = s.evaluated_parcels
                                   AND actual.inside_count = s.inside_count
                                   AND actual.outside_count = s.outside_count
                                   AND actual.boundary_review_count = s.boundary_review_count
                        WHERE b.status = 'succeeded_unchanged'
                          AND b.activation_id = :activation_id
                          AND b.completed_at IS NOT NULL
                          AND b.expected_parcels = b.evaluated_parcels
                          AND (c.payload ->> 'status') IN ('succeeded','succeeded_unchanged')
                          AND (c.payload ->> 'run_profile') = 'cohort'
                          AND NOT (c.payload ->> 'partial')::boolean
                          AND (c.payload ->> 'records_quarantined')::integer = 0
                          AND (c.payload ->> 'records_fetched')::integer = s.expected_parcels
                          AND jsonb_array_length(c.payload -> 'artifact_ids') > 0
                          AND NOT EXISTS (
                              SELECT 1
                              FROM geo.opportunity_zone_membership AS lineage_membership
                              JOIN geo.parcel_geometry AS lineage_geometry
                                ON lineage_geometry.observation_id =
                                   lineage_membership.parcel_geometry_observation_id
                              WHERE lineage_membership.membership_snapshot_id = s.id
                                AND (
                                    lineage_geometry.source_id IS DISTINCT FROM
                                        s.parcel_source_id
                                    OR lineage_geometry.parser_version IS DISTINCT FROM
                                        (c.payload ->> 'parser_version')
                                    OR jsonb_typeof(c.payload -> 'artifact_ids')
                                        IS DISTINCT FROM 'array'
                                    OR NOT COALESCE(
                                        (c.payload -> 'artifact_ids')
                                            ? lineage_geometry.source_artifact_id::text,
                                        false
                                    )
                                )
                          )
                          AND r.census_vintage = :census_vintage
                          AND r.designation_status = 'effective'
                          AND (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date
                              BETWEEN r.effective_from AND r.effective_to
                          AND EXISTS (
                              SELECT 1
                              FROM geo.opportunity_zone_membership_build_run AS initial
                              WHERE initial.id <> b.id
                                AND initial.snapshot_id = b.snapshot_id
                                AND initial.status = 'succeeded'
                                AND initial.activation_id = b.activation_id
                                AND initial.started_at <= b.started_at
                          )
                          AND (
                              SELECT count(*)
                              FROM geo.opportunity_zone_tract AS frozen
                              WHERE frozen.round_id = s.round_id
                                AND frozen.census_vintage = :census_vintage
                                AND frozen.designation_status = 'effective'
                          ) = :expected_tracts
                          AND (
                              SELECT count(*)
                              FROM geo.opportunity_zone_tract AS repaired
                              WHERE repaired.round_id = s.round_id
                                AND repaired.geometry_was_repaired
                          ) = :expected_repairs
                          AND NOT EXISTS (
                              SELECT 1
                              FROM geo.opportunity_zone_tract AS dated
                              WHERE dated.round_id = s.round_id
                                AND (
                                    s.effective_on BETWEEN dated.effective_from
                                                       AND dated.effective_to
                                ) IS DISTINCT FROM (
                                    (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date
                                        BETWEEN dated.effective_from AND dated.effective_to
                                )
                          )
                        """
                    ),
                    {
                        "cohort_run_id": cohort_run_id,
                        "round_id": CDFI_QOZ_2018_ROUND_ID,
                        "algorithm_version": OZ_MEMBERSHIP_ALGORITHM_VERSION,
                        "activation_id": OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
                        "census_vintage": CDFI_QOZ_2018_CENSUS_VINTAGE,
                        "expected_tracts": self.expected_tracts,
                        "expected_repairs": self.expected_designation_repairs,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if snapshot is None:
                reason = self._unavailable_reason(
                    connection,
                    cohort_run_id=cohort_run_id,
                    parcel_ids=parcel_ids,
                )
                return OpportunityZoneSnapshot(
                    cohort_run_id=cohort_run_id,
                    complete=False,
                    unavailable_reason=reason,
                )
            rows = (
                connection.execute(
                    sa.text(
                        """
                        SELECT m.parcel_id, m.classification, m.tract_geoid,
                               m.intersecting_tract_geoids,
                               m.designation_geometry_was_repaired,
                               m.designation_geometry_repair_method, m.classified_at,
                               pg.source_id AS parcel_source_id,
                               pg.source_record_id AS parcel_source_record_id,
                               pg.source_artifact_sha256 AS parcel_artifact_sha256,
                               pg.observed_at AS parcel_observed_at,
                               pg.geometry_was_repaired, pg.geometry_repair_method,
                               r.id AS round_id, r.census_vintage, r.designation_status,
                               COALESCE(t.effective_from, r.effective_from) AS effective_from,
                               COALESCE(t.effective_to, r.effective_to) AS effective_to,
                               r.source_id AS designation_source_id,
                               r.source_artifact_sha256 AS designation_artifact_sha256,
                               r.authority_uri
                        FROM geo.opportunity_zone_membership AS m
                        JOIN geo.parcel_geometry AS pg
                          ON pg.observation_id = m.parcel_geometry_observation_id
                        JOIN geo.opportunity_zone_round AS r
                          ON r.id = m.round_id
                         AND r.census_vintage = :census_vintage
                         AND r.designation_status = 'effective'
                        LEFT JOIN geo.opportunity_zone_tract AS t
                          ON t.round_id = m.round_id AND t.tract_geoid = m.tract_geoid
                        WHERE m.membership_snapshot_id = :snapshot_id
                          AND m.parcel_id = ANY(:parcel_ids)
                        ORDER BY m.parcel_id
                        """
                    ),
                    {
                        "snapshot_id": snapshot["id"],
                        "parcel_ids": list(parcel_ids),
                        "census_vintage": CDFI_QOZ_2018_CENSUS_VINTAGE,
                    },
                )
                .mappings()
                .all()
            )
        if len(rows) != len(set(parcel_ids)):
            return OpportunityZoneSnapshot(
                cohort_run_id=cohort_run_id,
                complete=False,
                unavailable_reason=OpportunityZoneEvidenceReason.MEMBERSHIP_SNAPSHOT_UNAVAILABLE,
            )
        memberships = tuple(_membership_record(cast(Mapping[str, object], row)) for row in rows)
        return OpportunityZoneSnapshot(
            cohort_run_id=cohort_run_id,
            complete=True,
            memberships=memberships,
        )

    def _require_verified_import_replay(
        self,
        connection: sa.Connection,
        *,
        expected_tracts: int,
        effective_at: datetime,
    ) -> None:
        latest = (
            connection.execute(
                sa.text(
                    """
                    SELECT i.id, i.status, i.activation_id, i.started_at,
                           i.source_artifact_id, i.source_artifact_sha256,
                           i.expected_tracts, i.imported_tracts,
                           r.source_artifact_id AS round_artifact_id,
                           r.source_artifact_sha256 AS round_artifact_sha256,
                           r.census_vintage, r.designation_status,
                           r.effective_from, r.effective_to
                    FROM geo.opportunity_zone_import_run AS i
                    LEFT JOIN geo.opportunity_zone_round AS r ON r.id = :round_id
                    WHERE i.source_id = :source_id
                    ORDER BY i.started_at DESC, i.id DESC
                    LIMIT 1
                    """
                ),
                {
                    "round_id": CDFI_QOZ_2018_ROUND_ID,
                    "source_id": CDFI_QOZ_2018_SOURCE_ID,
                },
            )
            .mappings()
            .one_or_none()
        )
        if latest is None or not (
            latest["status"] == "succeeded_unchanged"
            and latest["activation_id"] == CDFI_QOZ_2018_ACTIVATION_ID
            and int(latest["expected_tracts"]) == expected_tracts
            and int(latest["imported_tracts"]) == expected_tracts
            and latest["source_artifact_id"] is not None
            and latest["source_artifact_sha256"] == self.expected_designation_sha256
            and latest["source_artifact_id"] == latest["round_artifact_id"]
            and latest["source_artifact_sha256"] == latest["round_artifact_sha256"]
            and int(latest["census_vintage"] or 0) == CDFI_QOZ_2018_CENSUS_VINTAGE
            and latest["designation_status"] == "effective"
            and latest["effective_from"]
            <= effective_at.astimezone(UTC).date()
            <= latest["effective_to"]
        ):
            raise OpportunityZoneMembershipError(
                "membership build requires the exact successful unchanged static QOZ import replay"
            )

        initial_success = int(
            connection.scalar(
                sa.text(
                    """
                    SELECT count(*)
                    FROM geo.opportunity_zone_import_run
                    WHERE source_id = :source_id
                      AND id <> :latest_id
                      AND status = 'succeeded'
                      AND activation_id = :activation_id
                      AND source_artifact_id = :artifact_id
                      AND source_artifact_sha256 = :artifact_sha256
                      AND expected_tracts = :expected_tracts
                      AND imported_tracts = :expected_tracts
                      AND started_at <= :latest_started_at
                    """
                ),
                {
                    "source_id": CDFI_QOZ_2018_SOURCE_ID,
                    "latest_id": latest["id"],
                    "activation_id": CDFI_QOZ_2018_ACTIVATION_ID,
                    "artifact_id": latest["source_artifact_id"],
                    "artifact_sha256": latest["source_artifact_sha256"],
                    "expected_tracts": expected_tracts,
                    "latest_started_at": latest["started_at"],
                },
            )
            or 0
        )
        active_layer = (
            connection.execute(
                sa.text(
                    """
                    SELECT count(*) AS frozen_tracts,
                           count(*) FILTER (WHERE geometry_was_repaired) AS repaired_tracts
                    FROM geo.opportunity_zone_tract
                    WHERE round_id = :round_id
                      AND census_vintage = :census_vintage
                      AND designation_status = 'effective'
                    """
                ),
                {
                    "round_id": CDFI_QOZ_2018_ROUND_ID,
                    "census_vintage": CDFI_QOZ_2018_CENSUS_VINTAGE,
                },
            )
            .mappings()
            .one()
        )
        if (
            initial_success < 1
            or int(active_layer["frozen_tracts"]) != expected_tracts
            or int(active_layer["repaired_tracts"]) != self.expected_designation_repairs
        ):
            raise OpportunityZoneMembershipError(
                "membership build requires the complete effective layer "
                "and its initial import proof"
            )

    @staticmethod
    def _require_replayed_build(
        connection: sa.Connection,
        *,
        cohort_run_id: UUID,
        snapshot_id: UUID,
        expected_parcels: int,
    ) -> Mapping[str, object]:
        replayed = (
            connection.execute(
                sa.text(
                    """
                    WITH latest AS (
                        SELECT *
                        FROM geo.opportunity_zone_membership_build_run
                        WHERE cohort_run_id = :cohort_run_id
                          AND round_id = :round_id
                          AND algorithm_version = :algorithm_version
                        ORDER BY started_at DESC, id DESC
                        LIMIT 1
                    )
                    SELECT latest.id, latest.started_at, latest.completed_at
                    FROM latest
                    WHERE status = 'succeeded_unchanged'
                      AND activation_id = :activation_id
                      AND snapshot_id = :snapshot_id
                      AND expected_parcels = :expected_parcels
                      AND evaluated_parcels = :expected_parcels
                      AND EXISTS (
                          SELECT 1
                          FROM geo.opportunity_zone_membership_build_run AS initial
                          WHERE initial.id <> latest.id
                            AND initial.snapshot_id = latest.snapshot_id
                            AND initial.status = 'succeeded'
                            AND initial.activation_id = latest.activation_id
                            AND initial.started_at <= latest.started_at
                      )
                    """
                ),
                {
                    "cohort_run_id": cohort_run_id,
                    "round_id": CDFI_QOZ_2018_ROUND_ID,
                    "algorithm_version": OZ_MEMBERSHIP_ALGORITHM_VERSION,
                    "activation_id": OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
                    "snapshot_id": snapshot_id,
                    "expected_parcels": expected_parcels,
                },
            )
            .mappings()
            .one_or_none()
        )
        if replayed is None:
            raise OpportunityZoneMembershipError(
                "membership verification requires the exact successful unchanged build replay"
            )
        return cast(Mapping[str, object], replayed)

    @staticmethod
    def _stage_cohort(connection: sa.Connection, *, cohort: SourceRun) -> None:
        connection.execute(
            sa.text(
                """
                CREATE TEMPORARY TABLE oz_parcel_stage ON COMMIT DROP AS
                WITH ranked AS (
                    SELECT o.id AS observation_id,
                           o.jurisdiction_id,
                           o.local_parcel_id,
                           row_number() OVER (
                               PARTITION BY o.local_parcel_id
                               ORDER BY o.observed_at DESC, o.id DESC
                           ) AS position
                    FROM observation.parcel_observation AS o
                    WHERE o.source_id = :source_id
                      AND o.artifact_id = ANY(:artifact_ids)
                      AND o.parser_version = :parser_version
                )
                SELECT i.id AS parcel_id, ranked.observation_id,
                       g.geometry, g.geometry_was_repaired, g.geometry_repair_method
                FROM ranked
                LEFT JOIN identity.parcel AS i
                  ON i.jurisdiction_id = ranked.jurisdiction_id
                 AND i.local_parcel_id = ranked.local_parcel_id
                LEFT JOIN geo.parcel_geometry AS g
                  ON g.observation_id = ranked.observation_id AND g.parcel_id = i.id
                WHERE ranked.position = 1
                """
            ),
            {
                "source_id": cohort.source_id,
                "artifact_ids": list(cohort.artifact_ids),
                "parser_version": cohort.parser_version,
            },
        )

    @staticmethod
    def _classify(connection: sa.Connection, *, classified_at: datetime) -> None:
        connection.execute(
            sa.text(
                """
                CREATE TEMPORARY TABLE oz_membership_stage ON COMMIT DROP AS
                WITH hits AS (
                    SELECT p.parcel_id, p.observation_id, p.geometry_was_repaired,
                           p.geometry_repair_method,
                           z.tract_geoid, z.geometry_was_repaired
                               AS designation_geometry_was_repaired,
                           z.geometry_repair_method AS designation_geometry_repair_method,
                           ST_Within(p.geometry, z.geometry)
                               AND NOT ST_Intersects(p.geometry, ST_Boundary(z.geometry))
                               AS strict_interior
                    FROM oz_parcel_stage AS p
                    LEFT JOIN geo.opportunity_zone_tract AS z
                      ON z.round_id = :round_id
                     AND z.census_vintage = :census_vintage
                     AND z.designation_status = 'effective'
                     AND (:classified_at AT TIME ZONE 'UTC')::date
                         BETWEEN z.effective_from AND z.effective_to
                     AND p.geometry && z.geometry
                     AND ST_Intersects(p.geometry, z.geometry)
                ), aggregated AS (
                    SELECT parcel_id, observation_id, geometry_was_repaired,
                           geometry_repair_method,
                           COALESCE(
                               array_agg(tract_geoid ORDER BY tract_geoid)
                                   FILTER (WHERE tract_geoid IS NOT NULL),
                               ARRAY[]::varchar(11)[]
                           ) AS intersecting_tract_geoids,
                           count(tract_geoid) AS hit_count,
                           bool_or(strict_interior) FILTER (WHERE tract_geoid IS NOT NULL)
                               AS has_strict_interior,
                           COALESCE(
                               bool_or(designation_geometry_was_repaired)
                                   FILTER (WHERE tract_geoid IS NOT NULL),
                               false
                           ) AS designation_geometry_was_repaired,
                           COALESCE(
                               array_agg(
                                   DISTINCT designation_geometry_repair_method
                                   ORDER BY designation_geometry_repair_method
                               ) FILTER (
                                   WHERE designation_geometry_was_repaired
                                     AND designation_geometry_repair_method IS NOT NULL
                               ),
                               ARRAY[]::text[]
                           ) AS designation_geometry_repair_methods
                    FROM hits
                    GROUP BY parcel_id, observation_id, geometry_was_repaired,
                             geometry_repair_method
                )
                SELECT parcel_id, observation_id,
                       CASE
                           WHEN designation_geometry_was_repaired THEN 'boundary_review'
                           WHEN geometry_was_repaired THEN 'boundary_review'
                           WHEN hit_count = 0 THEN 'outside'
                           WHEN hit_count = 1 AND has_strict_interior THEN 'inside'
                           ELSE 'boundary_review'
                       END AS classification,
                       CASE
                           WHEN NOT designation_geometry_was_repaired
                            AND NOT geometry_was_repaired
                            AND hit_count = 1 AND has_strict_interior
                           THEN intersecting_tract_geoids[1]
                           ELSE NULL
                       END AS tract_geoid,
                       intersecting_tract_geoids,
                       geometry_was_repaired AS parcel_geometry_was_repaired,
                       geometry_repair_method AS parcel_geometry_repair_method,
                       designation_geometry_was_repaired,
                       CASE
                           WHEN cardinality(designation_geometry_repair_methods) = 1
                           THEN designation_geometry_repair_methods[1]
                           ELSE NULL
                       END AS designation_geometry_repair_method,
                       designation_geometry_repair_methods,
                       CAST(:classified_at AS timestamptz) AS classified_at
                FROM aggregated
                """
            ),
            {
                "round_id": CDFI_QOZ_2018_ROUND_ID,
                "census_vintage": CDFI_QOZ_2018_CENSUS_VINTAGE,
                "classified_at": classified_at,
            },
        )

    @staticmethod
    def _validate_designation_repair_lineage(connection: sa.Connection) -> None:
        invalid = int(
            connection.scalar(
                sa.text(
                    """
                    SELECT count(*)
                    FROM oz_membership_stage
                    WHERE (classification = 'boundary_review'
                           AND cardinality(intersecting_tract_geoids) = 0
                           AND NOT parcel_geometry_was_repaired)
                       OR (parcel_geometry_was_repaired AND (
                               parcel_geometry_repair_method IS NULL
                               OR classification <> 'boundary_review'
                           ))
                       OR (NOT parcel_geometry_was_repaired
                           AND parcel_geometry_repair_method IS NOT NULL)
                       OR (designation_geometry_was_repaired AND (
                               cardinality(designation_geometry_repair_methods) <> 1
                               OR designation_geometry_repair_method IS NULL
                           ))
                       OR (NOT designation_geometry_was_repaired AND (
                               cardinality(designation_geometry_repair_methods) <> 0
                               OR designation_geometry_repair_method IS NOT NULL
                           ))
                    """
                )
            )
            or 0
        )
        if invalid:
            raise OpportunityZoneMembershipError(
                "boundary classification or designation repair lineage is incomplete"
            )

    @staticmethod
    def _classification_counts(connection: sa.Connection) -> dict[str, int]:
        row = (
            connection.execute(
                sa.text(
                    """
                SELECT count(*) AS evaluated_parcels,
                       count(*) FILTER (WHERE classification = 'inside') AS inside_count,
                       count(*) FILTER (WHERE classification = 'outside') AS outside_count,
                       count(*) FILTER (WHERE classification = 'boundary_review')
                           AS boundary_review_count
                FROM oz_membership_stage
                """
                )
            )
            .mappings()
            .one()
        )
        return {key: int(row[key]) for key in row}

    def _insert_build_receipt(
        self,
        *,
        build_id: UUID,
        cohort: SourceRun,
        activation_id: str,
        started_at: datetime,
        effective_on: date,
        expected_parcels: int,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO geo.opportunity_zone_membership_build_run (
                        id, parcel_source_id, cohort_run_id, round_id, algorithm_version,
                        activation_id, effective_on, status, started_at, expected_parcels
                    ) VALUES (
                        :id, :parcel_source_id, :cohort_run_id, :round_id, :algorithm_version,
                        :activation_id, :effective_on, 'running', :started_at, :expected_parcels
                    )
                    """
                ),
                {
                    "id": build_id,
                    "parcel_source_id": cohort.source_id,
                    "cohort_run_id": cohort.id,
                    "round_id": CDFI_QOZ_2018_ROUND_ID,
                    "algorithm_version": OZ_MEMBERSHIP_ALGORITHM_VERSION,
                    "activation_id": activation_id,
                    "effective_on": effective_on,
                    "started_at": started_at,
                    "expected_parcels": expected_parcels,
                },
            )

    @staticmethod
    def _complete_build_receipt(
        connection: sa.Connection,
        *,
        build_id: UUID,
        snapshot_id: UUID,
        status: OpportunityZoneMembershipBuildStatus,
        counts: Mapping[str, int],
        completed_at: datetime,
    ) -> None:
        result = connection.execute(
            sa.text(
                """
                UPDATE geo.opportunity_zone_membership_build_run
                SET status = :status, completed_at = :completed_at, snapshot_id = :snapshot_id,
                    evaluated_parcels = :evaluated_parcels, inside_count = :inside_count,
                    outside_count = :outside_count,
                    boundary_review_count = :boundary_review_count,
                    missing_geometry_count = 0, error_code = NULL, error_detail = NULL
                WHERE id = :build_id AND status = 'running'
                """
            ),
            {
                "build_id": build_id,
                "snapshot_id": snapshot_id,
                "status": status.value,
                "completed_at": completed_at,
                **counts,
            },
        )
        if result.rowcount != 1:
            raise OpportunityZoneMembershipError(
                "membership build receipt did not complete exactly one running attempt"
            )

    def _fail_build_receipt(
        self,
        *,
        build_id: UUID,
        error: Exception,
        completed_at: datetime,
    ) -> None:
        try:
            with self.engine.begin() as connection:
                result = connection.execute(
                    sa.text(
                        """
                        UPDATE geo.opportunity_zone_membership_build_run
                        SET status = 'failed', completed_at = :completed_at,
                            error_code = :error_code, error_detail = :error_detail
                        WHERE id = :build_id AND status = 'running'
                        """
                    ),
                    {
                        "build_id": build_id,
                        "completed_at": completed_at,
                        "error_code": type(error).__name__,
                        "error_detail": durable_error_detail(
                            error,
                            database_fallback=(
                                "Database persistence rejected the membership build; "
                                "statement parameters were withheld."
                            ),
                        ),
                    },
                )
                if result.rowcount != 1:
                    raise OpportunityZoneMembershipError(
                        "membership build failure receipt did not close exactly one attempt"
                    )
        except sa.exc.SQLAlchemyError:
            pass

    @staticmethod
    def _latest_applicable_snapshot_id(
        connection: sa.Connection,
        *,
        cohort_run_id: UUID,
    ) -> UUID | None:
        value = connection.scalar(
            sa.text(
                """
                SELECT s.id
                FROM geo.opportunity_zone_membership_snapshot AS s
                JOIN geo.opportunity_zone_round AS r ON r.id = s.round_id
                WHERE s.cohort_run_id = :cohort_run_id
                  AND s.round_id = :round_id
                  AND s.algorithm_version = :algorithm_version
                  AND (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date
                      BETWEEN r.effective_from AND r.effective_to
                  AND NOT EXISTS (
                      SELECT 1
                      FROM geo.opportunity_zone_tract AS dated
                      WHERE dated.round_id = s.round_id
                        AND (
                            s.effective_on BETWEEN dated.effective_from AND dated.effective_to
                        ) IS DISTINCT FROM (
                            (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date
                                BETWEEN dated.effective_from AND dated.effective_to
                        )
                  )
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT 1
                """
            ),
            {
                "cohort_run_id": cohort_run_id,
                "round_id": CDFI_QOZ_2018_ROUND_ID,
                "algorithm_version": OZ_MEMBERSHIP_ALGORITHM_VERSION,
            },
        )
        return cast(UUID | None, value)

    @staticmethod
    def _existing_snapshot(
        connection: sa.Connection,
        *,
        snapshot_id: UUID,
    ) -> dict[str, int] | None:
        row = (
            connection.execute(
                sa.text(
                    """
                    SELECT evaluated_parcels, inside_count, outside_count, boundary_review_count
                    FROM geo.opportunity_zone_membership_snapshot WHERE id = :snapshot_id
                    """
                ),
                {"snapshot_id": snapshot_id},
            )
            .mappings()
            .one_or_none()
        )
        return {key: int(row[key]) for key in row} if row is not None else None

    @staticmethod
    def _verify_snapshot_rows(
        connection: sa.Connection,
        *,
        snapshot_id: UUID,
        expected_parcels: int,
        expected: Mapping[str, int],
    ) -> None:
        row = (
            connection.execute(
                sa.text(
                    """
                SELECT count(*) AS evaluated_parcels,
                       count(*) FILTER (WHERE classification = 'inside') AS inside_count,
                       count(*) FILTER (WHERE classification = 'outside') AS outside_count,
                       count(*) FILTER (WHERE classification = 'boundary_review')
                           AS boundary_review_count
                FROM geo.opportunity_zone_membership
                WHERE membership_snapshot_id = :snapshot_id
                """
                ),
                {"snapshot_id": snapshot_id},
            )
            .mappings()
            .one()
        )
        actual = {key: int(row[key]) for key in row}
        if actual != dict(expected) or actual["evaluated_parcels"] != expected_parcels:
            raise OpportunityZoneMembershipError(
                "stored membership snapshot is incomplete or conflicts with its receipt"
            )

    @staticmethod
    def _verify_snapshot_replay_rows(
        connection: sa.Connection,
        *,
        snapshot_id: UUID,
    ) -> None:
        differences = int(
            connection.scalar(
                sa.text(
                    """
                    WITH staged AS (
                        SELECT parcel_id,
                               observation_id AS parcel_geometry_observation_id,
                               classification,
                               tract_geoid,
                               intersecting_tract_geoids,
                               parcel_geometry_was_repaired,
                               parcel_geometry_repair_method,
                               designation_geometry_was_repaired,
                               designation_geometry_repair_method,
                               (classified_at AT TIME ZONE 'UTC')::date AS effective_on
                        FROM oz_membership_stage
                    ), stored AS (
                        SELECT parcel_id,
                               parcel_geometry_observation_id,
                               classification,
                               tract_geoid,
                               intersecting_tract_geoids,
                               parcel_geometry_was_repaired,
                               parcel_geometry_repair_method,
                               designation_geometry_was_repaired,
                               designation_geometry_repair_method,
                               effective_on
                        FROM geo.opportunity_zone_membership
                        WHERE membership_snapshot_id = :snapshot_id
                    ), differences AS (
                        (SELECT * FROM staged EXCEPT ALL SELECT * FROM stored)
                        UNION ALL
                        (SELECT * FROM stored EXCEPT ALL SELECT * FROM staged)
                    )
                    SELECT count(*) FROM differences
                    """
                ),
                {"snapshot_id": snapshot_id},
            )
            or 0
        )
        if differences:
            raise OpportunityZoneMembershipError(
                "stored membership evidence differs from deterministic spatial replay"
            )

    @staticmethod
    def _require_snapshot_cohort_lineage(
        connection: sa.Connection,
        *,
        snapshot_id: UUID,
    ) -> None:
        invalid = int(
            connection.scalar(
                sa.text(
                    """
                    SELECT count(*)
                    FROM geo.opportunity_zone_membership AS m
                    JOIN geo.opportunity_zone_membership_snapshot AS s
                      ON s.id = m.membership_snapshot_id
                    JOIN registry.source_run AS c
                      ON c.id = s.cohort_run_id
                     AND c.source_id = s.parcel_source_id
                    JOIN geo.parcel_geometry AS pg
                      ON pg.observation_id = m.parcel_geometry_observation_id
                    WHERE m.membership_snapshot_id = :snapshot_id
                      AND (
                          pg.source_id IS DISTINCT FROM s.parcel_source_id
                          OR pg.parser_version IS DISTINCT FROM
                              (c.payload ->> 'parser_version')
                          OR jsonb_typeof(c.payload -> 'artifact_ids')
                              IS DISTINCT FROM 'array'
                          OR NOT COALESCE(
                              (c.payload -> 'artifact_ids') ? pg.source_artifact_id::text,
                              false
                          )
                      )
                    """
                ),
                {"snapshot_id": snapshot_id},
            )
            or 0
        )
        if invalid:
            raise OpportunityZoneMembershipError(
                "stored membership geometry conflicts with its cohort artifact/parser lineage"
            )

    def _unavailable_reason(
        self,
        connection: sa.Connection,
        *,
        cohort_run_id: UUID,
        parcel_ids: tuple[UUID, ...],
    ) -> OpportunityZoneEvidenceReason:
        layer = (
            connection.execute(
                sa.text(
                    "SELECT count(*) AS frozen_tracts, "
                    "count(*) FILTER (WHERE geometry_was_repaired) AS repaired_tracts "
                    "FROM geo.opportunity_zone_tract "
                    "WHERE round_id = :round_id "
                    "AND census_vintage = :census_vintage "
                    "AND designation_status = 'effective'"
                ),
                {
                    "round_id": CDFI_QOZ_2018_ROUND_ID,
                    "census_vintage": CDFI_QOZ_2018_CENSUS_VINTAGE,
                },
            )
            .mappings()
            .one()
        )
        if (
            int(layer["frozen_tracts"]) != self.expected_tracts
            or int(layer["repaired_tracts"]) != self.expected_designation_repairs
        ):
            return OpportunityZoneEvidenceReason.DESIGNATION_LAYER_UNAVAILABLE
        geometry_count = int(
            connection.scalar(
                sa.text(
                    "SELECT count(DISTINCT parcel_id) FROM geo.parcel_geometry "
                    "WHERE parcel_id = ANY(:parcel_ids)"
                ),
                {"parcel_ids": list(parcel_ids)},
            )
            or 0
        )
        if geometry_count < len(set(parcel_ids)):
            return OpportunityZoneEvidenceReason.PARCEL_GEOMETRY_UNAVAILABLE
        del cohort_run_id
        return OpportunityZoneEvidenceReason.MEMBERSHIP_SNAPSHOT_UNAVAILABLE


class OpportunityZoneMembershipService:
    def __init__(
        self,
        *,
        acquisition: AcquisitionRepository,
        memberships: PostgresOpportunityZoneMembershipRepository,
        dispose: Callable[[], None] = lambda: None,
    ) -> None:
        self.acquisition = acquisition
        self.memberships = memberships
        self.dispose = dispose

    def close(self) -> None:
        self.dispose()

    def build(
        self,
        *,
        build_enabled: bool,
        activation_id: str | None,
    ) -> OpportunityZoneMembershipBuildOutcome:
        if not build_enabled:
            raise OpportunityZoneMembershipBuildDisabledError(
                "2018 QOZ membership build kill switch is disabled"
            )
        if activation_id != OZ_MEMBERSHIP_BUILD_ACTIVATION_ID:
            raise OpportunityZoneMembershipBuildDisabledError(
                "2018 QOZ membership build requires the exact reviewed activation ID"
            )
        cohort = self._latest_complete_cohort()
        return self.memberships.build_snapshot(
            cohort=cohort,
            activation_id=activation_id,
            expected_parcels=cohort.records_fetched,
        )

    def verify(self) -> OpportunityZoneMembershipBuildOutcome:
        cohort = self._latest_complete_cohort()
        return self.memberships.verify_snapshot(
            cohort=cohort,
            expected_parcels=cohort.records_fetched,
        )

    def _latest_complete_cohort(self) -> SourceRun:
        latest_attempt = self.acquisition.latest_run(
            "travis_tcad_parcels",
            run_profile=SourceRunProfile.COHORT,
        )
        if latest_attempt is None:
            raise OpportunityZoneMembershipError(
                "no TCAD cohort attempt is available for membership"
            )
        if not latest_attempt.is_complete_cohort:
            raise OpportunityZoneMembershipError(
                "latest TCAD cohort attempt is not complete; membership build is refused"
            )
        cohort = self.acquisition.latest_complete_run(
            "travis_tcad_parcels",
            run_profile=SourceRunProfile.COHORT,
        )
        if cohort is None or cohort.id != latest_attempt.id:
            raise OpportunityZoneMembershipError(
                "latest complete TCAD cohort does not match the latest cohort attempt"
            )
        if cohort.records_fetched <= 0:
            raise OpportunityZoneMembershipError("complete TCAD cohort is empty")
        return cohort


def _membership_record(row: Mapping[str, object]) -> OpportunityZoneMembershipRecord:
    classification = OpportunityZoneClassification(str(row["classification"]))
    parcel_repaired = bool(row["geometry_was_repaired"])
    designation_repaired = bool(row["designation_geometry_was_repaired"])
    reason = (
        OpportunityZoneEvidenceReason.DESIGNATION_GEOMETRY_REPAIRED
        if designation_repaired
        else OpportunityZoneEvidenceReason.PARCEL_GEOMETRY_REPAIRED
        if parcel_repaired
        else OpportunityZoneEvidenceReason.MATCHED_DESIGNATED_TRACT
        if classification is OpportunityZoneClassification.INSIDE
        else OpportunityZoneEvidenceReason.NO_DESIGNATED_TRACT_INTERSECTION
        if classification is OpportunityZoneClassification.OUTSIDE
        else OpportunityZoneEvidenceReason.PARCEL_INTERSECTS_DESIGNATION_BOUNDARY
    )
    return OpportunityZoneMembershipRecord(
        parcel_id=UUID(str(row["parcel_id"])),
        evidence=OpportunityZoneEvidence(
            classification=classification,
            reason_code=reason,
            method=OZ_MEMBERSHIP_ALGORITHM_VERSION,
            classified_at=row["classified_at"],
            parcel_geometry=ParcelGeometryEvidence(
                source_id=str(row["parcel_source_id"]),
                source_record_id=str(row["parcel_source_record_id"]),
                artifact_sha256=str(row["parcel_artifact_sha256"]),
                observed_at=row["parcel_observed_at"],
                geometry_repaired=parcel_repaired,
                repair_method=(
                    str(row["geometry_repair_method"])
                    if row["geometry_repair_method"] is not None
                    else None
                ),
            ),
            designation=OpportunityZoneDesignationEvidence(
                round_id=str(row["round_id"]),
                tract_geoid=str(row["tract_geoid"]) if row["tract_geoid"] else None,
                intersecting_tract_geoids=tuple(cast(list[str], row["intersecting_tract_geoids"])),
                census_vintage=int(str(row["census_vintage"])),
                designation_status="effective",
                effective_from=row["effective_from"],
                effective_to=row["effective_to"],
                source_id=str(row["designation_source_id"]),
                source_artifact_sha256=str(row["designation_artifact_sha256"]),
                authority_uri=str(row["authority_uri"]),
                geometry_repaired=designation_repaired,
                repair_method=(
                    str(row["designation_geometry_repair_method"])
                    if row["designation_geometry_repair_method"] is not None
                    else None
                ),
            ),
        ),
    )


def _outcome(
    *,
    build_id: UUID,
    cohort: SourceRun,
    activation_id: str,
    snapshot_id: UUID,
    status: OpportunityZoneMembershipBuildStatus,
    counts: Mapping[str, int],
    started_at: datetime,
    completed_at: datetime,
) -> OpportunityZoneMembershipBuildOutcome:
    return OpportunityZoneMembershipBuildOutcome(
        id=build_id,
        cohort_run_id=cohort.id,
        round_id=CDFI_QOZ_2018_ROUND_ID,
        algorithm_version=OZ_MEMBERSHIP_ALGORITHM_VERSION,
        activation_id=activation_id,
        status=status,
        snapshot_id=snapshot_id,
        expected_parcels=cohort.records_fetched,
        evaluated_parcels=counts["evaluated_parcels"],
        inside_count=counts["inside_count"],
        outside_count=counts["outside_count"],
        boundary_review_count=counts["boundary_review_count"],
        missing_geometry_count=0,
        started_at=started_at,
        completed_at=completed_at,
    )
