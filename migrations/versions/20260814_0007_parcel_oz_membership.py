"""Persist parcel geometry and versioned 2018 QOZ membership evidence.

Owning contexts: identity and geography.
Compatibility: additive; legacy parcel observations remain readable but have unavailable geography.
Backfill: none. A new complete TCAD cohort must supply geometry before membership can be built.

Revision ID: 20260814_0007
Revises: 20260813_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0007"
down_revision: str | Sequence[str] | None = "20260813_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

API_RUNTIME_ROLE = "seekandscore_api_runtime"
INGESTION_RUNTIME_ROLE = "seekandscore_ingestion_runtime"
OZ_IMPORTER_RUNTIME_ROLE = "seekandscore_oz_importer_runtime"
OZ_MEMBERSHIP_RUNTIME_ROLE = "seekandscore_oz_membership_runtime"

API_OZ_TRACT_SELECT_COLUMNS = (
    "round_id",
    "tract_geoid",
    "census_vintage",
    "certification_status",
    "designation_status",
    "effective_from",
    "effective_from_precision",
    "effective_to",
    "state_name",
    "county_name",
    "source_artifact_id",
    "source_artifact_sha256",
    "geometry_was_repaired",
    "geometry_repair_method",
    "loaded_at",
)
OZ_IMPORT_RUN_UPDATE_COLUMNS = (
    "status",
    "completed_at",
    "source_artifact_id",
    "source_artifact_sha256",
    "imported_tracts",
    "error_code",
    "error_detail",
)


class MultiPolygon3857(sa.types.UserDefinedType):  # type: ignore[type-arg]
    cache_ok = True

    def get_col_spec(self, **_kwargs: object) -> str:
        return "geometry(MULTIPOLYGON,3857)"


def upgrade() -> None:
    # Coordinate-bearing geometry is stored only in the typed, column-restricted geo table.
    # Scrub any pre-release v2 payloads before the API role can observe them through JSONB.
    op.execute(
        """
        UPDATE observation.parcel_observation
        SET payload = payload - 'geometry_geojson' - 'geometry_srid'
        WHERE payload ? 'geometry_geojson' OR payload ? 'geometry_srid'
        """
    )
    op.execute(
        """
        UPDATE registry.source_run
        SET payload = jsonb_set(
            payload,
            '{error_detail}',
            to_jsonb(
                'Database persistence failure detail was scrubbed during geometry rollout.'::text
            ),
            true
        )
        WHERE payload ->> 'parser_version' = 'travis-tcad-parcel-geometry-v2'
          AND payload ->> 'status' = 'failed'
          AND payload ->> 'error_detail' IS NOT NULL
        """
    )
    op.add_column(
        "parcel_observation",
        sa.Column(
            "jurisdiction_id",
            sa.Text(),
            sa.Computed("(payload ->> 'jurisdiction_id')", persisted=True),
            nullable=False,
        ),
        schema="observation",
    )
    op.add_column(
        "parcel_observation",
        sa.Column(
            "local_parcel_id",
            sa.Text(),
            sa.Computed("(payload ->> 'local_parcel_id')", persisted=True),
            nullable=False,
        ),
        schema="observation",
    )
    op.add_column(
        "parcel_observation",
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        schema="observation",
    )
    op.execute(
        "UPDATE observation.parcel_observation "
        "SET observed_at = (payload ->> 'observed_at')::timestamptz"
    )
    op.alter_column(
        "parcel_observation",
        "observed_at",
        nullable=False,
        schema="observation",
    )
    op.execute(
        """
        CREATE FUNCTION observation.validate_parcel_observation_lineage()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF NEW.source_id IS DISTINCT FROM (NEW.payload ->> 'source_id')
               OR NEW.source_record_id IS DISTINCT FROM (NEW.payload ->> 'source_record_id')
               OR NEW.artifact_id::text IS DISTINCT FROM (NEW.payload ->> 'artifact_id')
               OR NEW.artifact_sha256 IS DISTINCT FROM (NEW.payload ->> 'artifact_sha256')
               OR NEW.parser_version IS DISTINCT FROM (NEW.payload ->> 'parser_version')
               OR NEW.payload ->> 'observed_at' IS NULL
               OR NEW.observed_at IS DISTINCT FROM
                  ((NEW.payload ->> 'observed_at')::timestamptz) THEN
                RAISE EXCEPTION 'parcel observation lineage conflicts with its payload';
            END IF;
            RETURN NEW;
        END;
        $$;
        REVOKE ALL ON FUNCTION observation.validate_parcel_observation_lineage() FROM PUBLIC;
        CREATE TRIGGER trg_parcel_observation_validate_lineage
        BEFORE INSERT OR UPDATE ON observation.parcel_observation
        FOR EACH ROW EXECUTE FUNCTION observation.validate_parcel_observation_lineage();
        """
    )
    op.create_unique_constraint(
        "uq_raw_artifact_lineage_identity",
        "artifact",
        ["id", "source_id", "sha256"],
        schema="raw",
    )
    op.create_unique_constraint(
        "uq_registry_source_run_lineage_identity",
        "source_run",
        ["id", "source_id"],
        schema="registry",
    )
    op.create_foreign_key(
        "fk_observation_parcel_artifact_lineage",
        "parcel_observation",
        "artifact",
        ["artifact_id", "source_id", "artifact_sha256"],
        ["id", "source_id", "sha256"],
        source_schema="observation",
        referent_schema="raw",
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_observation_parcel_geometry_lineage",
        "parcel_observation",
        [
            "id",
            "source_id",
            "source_record_id",
            "artifact_id",
            "artifact_sha256",
            "parser_version",
            "jurisdiction_id",
            "local_parcel_id",
            "observed_at",
        ],
        schema="observation",
    )
    op.create_foreign_key(
        "fk_geo_oz_import_run_artifact_lineage",
        "opportunity_zone_import_run",
        "artifact",
        ["source_artifact_id", "source_id", "source_artifact_sha256"],
        ["id", "source_id", "sha256"],
        source_schema="geo",
        referent_schema="raw",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_geo_oz_round_artifact_lineage",
        "opportunity_zone_round",
        "artifact",
        ["source_artifact_id", "source_id", "source_artifact_sha256"],
        ["id", "source_id", "sha256"],
        source_schema="geo",
        referent_schema="raw",
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_geo_oz_round_tract_lineage",
        "opportunity_zone_round",
        ["id", "source_artifact_id", "source_artifact_sha256"],
        schema="geo",
    )
    op.create_foreign_key(
        "fk_geo_oz_tract_round_artifact_lineage",
        "opportunity_zone_tract",
        "opportunity_zone_round",
        ["round_id", "source_artifact_id", "source_artifact_sha256"],
        ["id", "source_artifact_id", "source_artifact_sha256"],
        source_schema="geo",
        referent_schema="geo",
        ondelete="RESTRICT",
    )

    op.create_table(
        "parcel",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jurisdiction_id", sa.Text(), nullable=False),
        sa.Column("local_parcel_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(jurisdiction_id)) > 0 AND length(trim(local_parcel_id)) > 0",
            name="ck_identity_parcel_nonempty_key",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_identity_parcel"),
        sa.UniqueConstraint(
            "jurisdiction_id",
            "local_parcel_id",
            name="uq_identity_parcel_jurisdiction_local",
        ),
        sa.UniqueConstraint(
            "id",
            "jurisdiction_id",
            "local_parcel_id",
            name="uq_identity_parcel_lineage",
        ),
        schema="identity",
    )
    op.create_table(
        "parcel_geometry",
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parcel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jurisdiction_id", sa.Text(), nullable=False),
        sa.Column("local_parcel_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=False),
        sa.Column("source_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=False),
        sa.Column("source_srid", sa.Integer(), nullable=False),
        sa.Column("geometry", MultiPolygon3857(), nullable=False),
        sa.Column("geometry_was_repaired", sa.Boolean(), nullable=False),
        sa.Column("geometry_repair_method", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_srid = 4326", name="ck_geo_parcel_geometry_source_srid"),
        sa.CheckConstraint(
            "source_artifact_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_geo_parcel_geometry_sha256",
        ),
        sa.CheckConstraint(
            "ST_IsValid(geometry) AND NOT ST_IsEmpty(geometry)",
            name="ck_geo_parcel_geometry_valid",
        ),
        sa.CheckConstraint(
            "(geometry_was_repaired AND geometry_repair_method IS NOT NULL) OR "
            "(NOT geometry_was_repaired AND geometry_repair_method IS NULL)",
            name="ck_geo_parcel_geometry_repair_lineage",
        ),
        sa.ForeignKeyConstraint(
            [
                "observation_id",
                "source_id",
                "source_record_id",
                "source_artifact_id",
                "source_artifact_sha256",
                "parser_version",
                "jurisdiction_id",
                "local_parcel_id",
                "observed_at",
            ],
            [
                "observation.parcel_observation.id",
                "observation.parcel_observation.source_id",
                "observation.parcel_observation.source_record_id",
                "observation.parcel_observation.artifact_id",
                "observation.parcel_observation.artifact_sha256",
                "observation.parcel_observation.parser_version",
                "observation.parcel_observation.jurisdiction_id",
                "observation.parcel_observation.local_parcel_id",
                "observation.parcel_observation.observed_at",
            ],
            name="fk_geo_parcel_geometry_observation_lineage",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parcel_id", "jurisdiction_id", "local_parcel_id"],
            [
                "identity.parcel.id",
                "identity.parcel.jurisdiction_id",
                "identity.parcel.local_parcel_id",
            ],
            name="fk_geo_parcel_geometry_parcel_lineage",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("observation_id", name="pk_geo_parcel_geometry"),
        sa.UniqueConstraint(
            "observation_id",
            "parcel_id",
            name="uq_geo_parcel_geometry_observation_parcel",
        ),
        schema="geo",
    )
    op.create_index(
        "ix_geo_parcel_geometry_parcel_observed",
        "parcel_geometry",
        ["parcel_id", sa.text("observed_at DESC")],
        schema="geo",
    )
    op.create_index(
        "ix_geo_parcel_geometry_geometry_gist",
        "parcel_geometry",
        ["geometry"],
        postgresql_using="gist",
        schema="geo",
    )

    # A snapshot is immutable and deterministic for cohort+round+algorithm+effective date.
    # Separate build-run receipts preserve every activated attempt, including unchanged replays.
    op.create_table(
        "opportunity_zone_membership_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parcel_source_id", sa.Text(), nullable=False),
        sa.Column("cohort_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_id", sa.Text(), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("activation_id", sa.Text(), nullable=False),
        sa.Column("effective_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_parcels", sa.Integer(), nullable=False),
        sa.Column("evaluated_parcels", sa.Integer(), nullable=False),
        sa.Column("inside_count", sa.Integer(), nullable=False),
        sa.Column("outside_count", sa.Integer(), nullable=False),
        sa.Column("boundary_review_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "length(trim(activation_id)) > 0",
            name="ck_geo_oz_membership_snapshot_activation",
        ),
        sa.CheckConstraint(
            "effective_on = (created_at AT TIME ZONE 'UTC')::date",
            name="ck_geo_oz_membership_snapshot_effective_date",
        ),
        sa.CheckConstraint(
            "expected_parcels > 0 AND evaluated_parcels = expected_parcels "
            "AND evaluated_parcels = inside_count + outside_count + boundary_review_count "
            "AND inside_count >= 0 AND outside_count >= 0 AND boundary_review_count >= 0",
            name="ck_geo_oz_membership_snapshot_complete",
        ),
        sa.ForeignKeyConstraint(
            ["cohort_run_id", "parcel_source_id"],
            ["registry.source_run.id", "registry.source_run.source_id"],
            name="fk_geo_oz_membership_snapshot_cohort",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["geo.opportunity_zone_round.id"],
            name="fk_geo_oz_membership_snapshot_round",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_geo_oz_membership_snapshot"),
        sa.UniqueConstraint(
            "cohort_run_id",
            "round_id",
            "algorithm_version",
            "effective_on",
            name="uq_geo_oz_membership_snapshot_version",
        ),
        sa.UniqueConstraint(
            "id",
            "round_id",
            "effective_on",
            name="uq_geo_oz_membership_snapshot_round_effective",
        ),
        sa.UniqueConstraint(
            "id",
            "parcel_source_id",
            "cohort_run_id",
            "round_id",
            "algorithm_version",
            "activation_id",
            "effective_on",
            "expected_parcels",
            "evaluated_parcels",
            "inside_count",
            "outside_count",
            "boundary_review_count",
            name="uq_geo_oz_membership_snapshot_build_lineage",
        ),
        schema="geo",
    )
    op.create_index(
        "ix_geo_oz_membership_snapshot_cohort_created",
        "opportunity_zone_membership_snapshot",
        ["cohort_run_id", sa.text("created_at DESC")],
        schema="geo",
    )

    op.create_table(
        "opportunity_zone_membership_build_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parcel_source_id", sa.Text(), nullable=False),
        sa.Column("cohort_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_id", sa.Text(), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("activation_id", sa.Text(), nullable=False),
        sa.Column("effective_on", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expected_parcels", sa.Integer(), nullable=False),
        sa.Column("evaluated_parcels", sa.Integer(), server_default="0", nullable=False),
        sa.Column("inside_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("outside_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("boundary_review_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("missing_geometry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(trim(activation_id)) > 0",
            name="ck_geo_oz_membership_build_activation",
        ),
        sa.CheckConstraint(
            "status IN ('running','succeeded','succeeded_unchanged','failed')",
            name="ck_geo_oz_membership_build_status",
        ),
        sa.CheckConstraint(
            "expected_parcels > 0 AND evaluated_parcels >= 0 "
            "AND inside_count >= 0 AND outside_count >= 0 "
            "AND boundary_review_count >= 0 AND missing_geometry_count >= 0",
            name="ck_geo_oz_membership_build_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "evaluated_parcels = inside_count + outside_count + boundary_review_count",
            name="ck_geo_oz_membership_build_classification_total",
        ),
        sa.CheckConstraint(
            "status NOT IN ('succeeded','succeeded_unchanged') OR "
            "(completed_at IS NOT NULL AND snapshot_id IS NOT NULL "
            "AND missing_geometry_count = 0 AND evaluated_parcels = expected_parcels)",
            name="ck_geo_oz_membership_build_complete_success",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND completed_at IS NULL AND snapshot_id IS NULL "
            "AND evaluated_parcels = 0 AND inside_count = 0 AND outside_count = 0 "
            "AND boundary_review_count = 0 AND missing_geometry_count = 0 "
            "AND error_code IS NULL AND error_detail IS NULL) OR "
            "(status = 'failed' AND completed_at IS NOT NULL AND snapshot_id IS NULL "
            "AND evaluated_parcels = 0 AND inside_count = 0 AND outside_count = 0 "
            "AND boundary_review_count = 0 AND missing_geometry_count = 0 "
            "AND error_code IS NOT NULL) OR "
            "(status IN ('succeeded','succeeded_unchanged') AND completed_at IS NOT NULL "
            "AND snapshot_id IS NOT NULL AND evaluated_parcels = expected_parcels "
            "AND missing_geometry_count = 0 AND error_code IS NULL AND error_detail IS NULL)",
            name="ck_geo_oz_membership_build_terminal_shape",
        ),
        sa.ForeignKeyConstraint(
            ["cohort_run_id", "parcel_source_id"],
            ["registry.source_run.id", "registry.source_run.source_id"],
            name="fk_geo_oz_membership_build_cohort",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["geo.opportunity_zone_round.id"],
            name="fk_geo_oz_membership_build_round",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "snapshot_id",
                "parcel_source_id",
                "cohort_run_id",
                "round_id",
                "algorithm_version",
                "activation_id",
                "effective_on",
                "expected_parcels",
                "evaluated_parcels",
                "inside_count",
                "outside_count",
                "boundary_review_count",
            ],
            [
                "geo.opportunity_zone_membership_snapshot.id",
                "geo.opportunity_zone_membership_snapshot.parcel_source_id",
                "geo.opportunity_zone_membership_snapshot.cohort_run_id",
                "geo.opportunity_zone_membership_snapshot.round_id",
                "geo.opportunity_zone_membership_snapshot.algorithm_version",
                "geo.opportunity_zone_membership_snapshot.activation_id",
                "geo.opportunity_zone_membership_snapshot.effective_on",
                "geo.opportunity_zone_membership_snapshot.expected_parcels",
                "geo.opportunity_zone_membership_snapshot.evaluated_parcels",
                "geo.opportunity_zone_membership_snapshot.inside_count",
                "geo.opportunity_zone_membership_snapshot.outside_count",
                "geo.opportunity_zone_membership_snapshot.boundary_review_count",
            ],
            name="fk_geo_oz_membership_build_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_geo_oz_membership_build"),
        schema="geo",
    )
    op.create_index(
        "ix_geo_oz_membership_build_cohort_started",
        "opportunity_zone_membership_build_run",
        ["cohort_run_id", sa.text("started_at DESC")],
        schema="geo",
    )

    op.create_table(
        "opportunity_zone_membership",
        sa.Column("membership_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_id", sa.Text(), nullable=False),
        sa.Column("parcel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parcel_geometry_observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classification", sa.Text(), nullable=False),
        sa.Column("tract_geoid", sa.String(length=11), nullable=True),
        sa.Column(
            "intersecting_tract_geoids",
            postgresql.ARRAY(sa.String(length=11)),
            nullable=False,
        ),
        sa.Column("parcel_geometry_was_repaired", sa.Boolean(), nullable=False),
        sa.Column("parcel_geometry_repair_method", sa.Text(), nullable=True),
        sa.Column("designation_geometry_was_repaired", sa.Boolean(), nullable=False),
        sa.Column("designation_geometry_repair_method", sa.Text(), nullable=True),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "effective_on",
            sa.Date(),
            sa.Computed("((classified_at AT TIME ZONE 'UTC')::date)", persisted=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "classification IN ('inside','outside','boundary_review')",
            name="ck_geo_oz_membership_classification",
        ),
        sa.CheckConstraint(
            "(classification = 'inside' AND tract_geoid IS NOT NULL "
            "AND cardinality(intersecting_tract_geoids) = 1 "
            "AND intersecting_tract_geoids[1] = tract_geoid) OR "
            "(classification = 'outside' AND tract_geoid IS NULL "
            "AND cardinality(intersecting_tract_geoids) = 0) OR "
            "(classification = 'boundary_review' AND tract_geoid IS NULL "
            "AND (cardinality(intersecting_tract_geoids) > 0 "
            "OR parcel_geometry_was_repaired))",
            name="ck_geo_oz_membership_evidence_shape",
        ),
        sa.CheckConstraint(
            "(parcel_geometry_was_repaired "
            "AND parcel_geometry_repair_method IS NOT NULL "
            "AND classification = 'boundary_review') OR "
            "(NOT parcel_geometry_was_repaired "
            "AND parcel_geometry_repair_method IS NULL)",
            name="ck_geo_oz_membership_parcel_repair_lineage",
        ),
        sa.CheckConstraint(
            "(designation_geometry_was_repaired "
            "AND designation_geometry_repair_method IS NOT NULL "
            "AND classification = 'boundary_review') OR "
            "(NOT designation_geometry_was_repaired "
            "AND designation_geometry_repair_method IS NULL)",
            name="ck_geo_oz_membership_designation_repair_lineage",
        ),
        sa.ForeignKeyConstraint(
            ["membership_snapshot_id", "round_id", "effective_on"],
            [
                "geo.opportunity_zone_membership_snapshot.id",
                "geo.opportunity_zone_membership_snapshot.round_id",
                "geo.opportunity_zone_membership_snapshot.effective_on",
            ],
            name="fk_geo_oz_membership_snapshot_round_effective",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parcel_id"],
            ["identity.parcel.id"],
            name="fk_geo_oz_membership_parcel",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parcel_geometry_observation_id", "parcel_id"],
            ["geo.parcel_geometry.observation_id", "geo.parcel_geometry.parcel_id"],
            name="fk_geo_oz_membership_geometry_parcel",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["round_id", "tract_geoid"],
            ["geo.opportunity_zone_tract.round_id", "geo.opportunity_zone_tract.tract_geoid"],
            name="fk_geo_oz_membership_tract",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "membership_snapshot_id",
            "parcel_id",
            name="pk_geo_oz_membership",
        ),
        schema="geo",
    )
    op.create_index(
        "ix_geo_oz_membership_parcel_snapshot",
        "opportunity_zone_membership",
        ["parcel_id", "membership_snapshot_id"],
        schema="geo",
    )
    op.execute(
        """
        CREATE FUNCTION geo.validate_oz_membership_geometry_lineage()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM geo.parcel_geometry AS pg
                WHERE pg.observation_id = NEW.parcel_geometry_observation_id
                  AND pg.parcel_id = NEW.parcel_id
                  AND pg.geometry_was_repaired IS NOT DISTINCT FROM
                      NEW.parcel_geometry_was_repaired
                  AND pg.geometry_repair_method IS NOT DISTINCT FROM
                      NEW.parcel_geometry_repair_method
            ) THEN
                RAISE EXCEPTION
                    'QOZ membership parcel-repair evidence conflicts with geometry lineage';
            END IF;
            RETURN NEW;
        END;
        $$;
        REVOKE ALL ON FUNCTION geo.validate_oz_membership_geometry_lineage() FROM PUBLIC;
        CREATE TRIGGER trg_oz_membership_validate_geometry_lineage
        BEFORE INSERT OR UPDATE ON geo.opportunity_zone_membership
        FOR EACH ROW EXECUTE FUNCTION geo.validate_oz_membership_geometry_lineage();
        """
    )

    op.create_check_constraint(
        "ck_geo_oz_import_run_terminal_shape",
        "opportunity_zone_import_run",
        "(status = 'running' AND completed_at IS NULL "
        "AND source_artifact_id IS NULL AND source_artifact_sha256 IS NULL "
        "AND imported_tracts = 0 AND error_code IS NULL AND error_detail IS NULL) OR "
        "(status = 'failed' AND completed_at IS NOT NULL AND imported_tracts = 0 "
        "AND error_code IS NOT NULL) OR "
        "(status IN ('succeeded','succeeded_unchanged') AND completed_at IS NOT NULL "
        "AND source_artifact_id IS NOT NULL AND source_artifact_sha256 IS NOT NULL "
        "AND imported_tracts = expected_tracts "
        "AND error_code IS NULL AND error_detail IS NULL)",
        schema="geo",
    )
    op.execute(
        """
        CREATE FUNCTION geo.validate_oz_import_run_transition()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'running' OR NEW.completed_at IS NOT NULL
                   OR NEW.source_artifact_id IS NOT NULL
                   OR NEW.source_artifact_sha256 IS NOT NULL
                   OR NEW.imported_tracts <> 0
                   OR NEW.error_code IS NOT NULL OR NEW.error_detail IS NOT NULL THEN
                    RAISE EXCEPTION 'QOZ import receipts must start in running state';
                END IF;
                RETURN NEW;
            END IF;
            IF OLD.status <> 'running' THEN
                RAISE EXCEPTION 'terminal QOZ import receipts are immutable';
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.source_id IS DISTINCT FROM OLD.source_id
               OR NEW.activation_id IS DISTINCT FROM OLD.activation_id
               OR NEW.started_at IS DISTINCT FROM OLD.started_at
               OR NEW.expected_tracts IS DISTINCT FROM OLD.expected_tracts THEN
                RAISE EXCEPTION 'QOZ import receipt identity is immutable';
            END IF;
            IF NEW.status = 'running' THEN
                RAISE EXCEPTION 'QOZ import receipt update must be terminal';
            END IF;
            RETURN NEW;
        END;
        $$;
        REVOKE ALL ON FUNCTION geo.validate_oz_import_run_transition() FROM PUBLIC;
        CREATE TRIGGER trg_oz_import_run_validate_transition
        BEFORE INSERT OR UPDATE ON geo.opportunity_zone_import_run
        FOR EACH ROW EXECUTE FUNCTION geo.validate_oz_import_run_transition();
        """
    )
    op.execute(
        """
        CREATE FUNCTION geo.validate_oz_membership_build_transition()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF NEW.effective_on IS DISTINCT FROM
               ((NEW.started_at AT TIME ZONE 'UTC')::date) THEN
                RAISE EXCEPTION 'QOZ membership effective date conflicts with its start time';
            END IF;
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'running' OR NEW.completed_at IS NOT NULL
                   OR NEW.snapshot_id IS NOT NULL OR NEW.evaluated_parcels <> 0
                   OR NEW.inside_count <> 0 OR NEW.outside_count <> 0
                   OR NEW.boundary_review_count <> 0 OR NEW.missing_geometry_count <> 0
                   OR NEW.error_code IS NOT NULL OR NEW.error_detail IS NOT NULL THEN
                    RAISE EXCEPTION 'QOZ membership receipts must start in running state';
                END IF;
                RETURN NEW;
            END IF;
            IF OLD.status <> 'running' THEN
                RAISE EXCEPTION 'terminal QOZ membership receipts are immutable';
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.parcel_source_id IS DISTINCT FROM OLD.parcel_source_id
               OR NEW.cohort_run_id IS DISTINCT FROM OLD.cohort_run_id
               OR NEW.round_id IS DISTINCT FROM OLD.round_id
               OR NEW.algorithm_version IS DISTINCT FROM OLD.algorithm_version
               OR NEW.activation_id IS DISTINCT FROM OLD.activation_id
               OR NEW.effective_on IS DISTINCT FROM OLD.effective_on
               OR NEW.started_at IS DISTINCT FROM OLD.started_at
               OR NEW.expected_parcels IS DISTINCT FROM OLD.expected_parcels THEN
                RAISE EXCEPTION 'QOZ membership receipt identity is immutable';
            END IF;
            IF NEW.status = 'running' THEN
                RAISE EXCEPTION 'QOZ membership receipt update must be terminal';
            END IF;
            RETURN NEW;
        END;
        $$;
        REVOKE ALL ON FUNCTION geo.validate_oz_membership_build_transition() FROM PUBLIC;
        CREATE TRIGGER trg_oz_membership_build_validate_transition
        BEFORE INSERT OR UPDATE ON geo.opportunity_zone_membership_build_run
        FOR EACH ROW EXECUTE FUNCTION geo.validate_oz_membership_build_transition();
        """
    )

    capability_roles = (OZ_IMPORTER_RUNTIME_ROLE, OZ_MEMBERSHIP_RUNTIME_ROLE)
    for role in capability_roles:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    CREATE ROLE {role}
                        NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                        NOINHERIT NOREPLICATION NOBYPASSRLS;
                END IF;
            END
            $$
            """
        )
        op.execute(
            f"ALTER ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
        )
        op.execute(
            f"""
            DO $$
            BEGIN
                EXECUTE format(
                    'REVOKE ALL PRIVILEGES ON DATABASE %I FROM {role}',
                    current_database()
                );
                EXECUTE format(
                    'GRANT CONNECT, TEMPORARY ON DATABASE %I TO {role}',
                    current_database()
                );
            END
            $$
            """
        )
    for schema in (
        "public",
        "platform",
        "registry",
        "raw",
        "observation",
        "identity",
        "geo",
        "market",
        "intelligence",
        "deal",
        "engagement",
        "delivery",
        "readmodel",
    ):
        for role in capability_roles:
            op.execute(f"REVOKE ALL PRIVILEGES ON SCHEMA {schema} FROM {role}")
            op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema} FROM {role}")
            op.execute(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema} FROM {role}")

    op.execute(f"GRANT USAGE ON SCHEMA identity, geo TO {API_RUNTIME_ROLE}")
    op.execute(
        f"GRANT SELECT ON identity.parcel, geo.opportunity_zone_round, "
        f"geo.opportunity_zone_membership_snapshot, "
        f"geo.opportunity_zone_membership_build_run, geo.opportunity_zone_membership "
        f"TO {API_RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT SELECT (observation_id, parcel_id, source_id, source_record_id, "
        f"source_artifact_id, source_artifact_sha256, parser_version, source_srid, "
        f"geometry_was_repaired, geometry_repair_method, observed_at) "
        f"ON geo.parcel_geometry TO {API_RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT SELECT ({', '.join(API_OZ_TRACT_SELECT_COLUMNS)}) "
        f"ON geo.opportunity_zone_tract TO {API_RUNTIME_ROLE}"
    )

    op.execute(f"GRANT USAGE ON SCHEMA identity, geo TO {INGESTION_RUNTIME_ROLE}")
    op.execute(f"GRANT SELECT ON public.spatial_ref_sys TO {INGESTION_RUNTIME_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT ON identity.parcel, geo.parcel_geometry TO {INGESTION_RUNTIME_ROLE}"
    )

    op.execute(f"GRANT USAGE ON SCHEMA registry, raw, geo TO {OZ_IMPORTER_RUNTIME_ROLE}")
    op.execute(
        f"GRANT SELECT ON registry.source_definition, raw.artifact, "
        f"geo.opportunity_zone_import_run, geo.opportunity_zone_round, "
        f"geo.opportunity_zone_tract TO {OZ_IMPORTER_RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT INSERT ON registry.source_definition, raw.artifact, "
        f"geo.opportunity_zone_import_run, geo.opportunity_zone_round, "
        f"geo.opportunity_zone_tract TO {OZ_IMPORTER_RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT UPDATE ({', '.join(OZ_IMPORT_RUN_UPDATE_COLUMNS)}) "
        f"ON geo.opportunity_zone_import_run TO {OZ_IMPORTER_RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT USAGE ON SCHEMA registry, observation, identity, geo "
        f"TO {OZ_MEMBERSHIP_RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT SELECT ON registry.source_run, observation.parcel_observation, "
        f"identity.parcel, geo.parcel_geometry, geo.opportunity_zone_import_run, "
        f"geo.opportunity_zone_round, "
        f"geo.opportunity_zone_tract, geo.opportunity_zone_membership_snapshot, "
        f"geo.opportunity_zone_membership_build_run, geo.opportunity_zone_membership "
        f"TO {OZ_MEMBERSHIP_RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT INSERT ON geo.opportunity_zone_membership_snapshot, "
        f"geo.opportunity_zone_membership_build_run, geo.opportunity_zone_membership "
        f"TO {OZ_MEMBERSHIP_RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT UPDATE (status, completed_at, evaluated_parcels, inside_count, outside_count, "
        f"boundary_review_count, missing_geometry_count, snapshot_id, error_code, error_detail) "
        f"ON geo.opportunity_zone_membership_build_run TO {OZ_MEMBERSHIP_RUNTIME_ROLE}"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_parcel_observation_validate_lineage "
        "ON observation.parcel_observation"
    )
    op.execute("DROP FUNCTION IF EXISTS observation.validate_parcel_observation_lineage()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_oz_membership_validate_geometry_lineage "
        "ON geo.opportunity_zone_membership"
    )
    op.execute("DROP FUNCTION IF EXISTS geo.validate_oz_membership_geometry_lineage()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_oz_membership_build_validate_transition "
        "ON geo.opportunity_zone_membership_build_run"
    )
    op.execute("DROP FUNCTION IF EXISTS geo.validate_oz_membership_build_transition()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_oz_import_run_validate_transition "
        "ON geo.opportunity_zone_import_run"
    )
    op.execute("DROP FUNCTION IF EXISTS geo.validate_oz_import_run_transition()")
    op.drop_constraint(
        "ck_geo_oz_import_run_terminal_shape",
        "opportunity_zone_import_run",
        schema="geo",
        type_="check",
    )
    for role in (OZ_IMPORTER_RUNTIME_ROLE, OZ_MEMBERSHIP_RUNTIME_ROLE):
        op.execute(
            f"""
            DO $$
            BEGIN
                EXECUTE format(
                    'REVOKE ALL PRIVILEGES ON DATABASE %I FROM {role}',
                    current_database()
                );
            END
            $$
            """
        )
        for schema in (
            "public",
            "platform",
            "registry",
            "raw",
            "observation",
            "identity",
            "geo",
            "market",
            "intelligence",
            "deal",
            "engagement",
            "delivery",
            "readmodel",
        ):
            op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema} FROM {role}")
            op.execute(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema} FROM {role}")
            op.execute(f"REVOKE ALL PRIVILEGES ON SCHEMA {schema} FROM {role}")
    for role in (
        API_RUNTIME_ROLE,
        INGESTION_RUNTIME_ROLE,
        OZ_IMPORTER_RUNTIME_ROLE,
        OZ_MEMBERSHIP_RUNTIME_ROLE,
    ):
        op.execute("REVOKE ALL PRIVILEGES ON geo.opportunity_zone_membership FROM " + role)
        op.execute(
            "REVOKE ALL PRIVILEGES ON geo.opportunity_zone_membership_build_run FROM " + role
        )
        op.execute("REVOKE ALL PRIVILEGES ON geo.opportunity_zone_membership_snapshot FROM " + role)
        op.execute("REVOKE ALL PRIVILEGES ON geo.parcel_geometry FROM " + role)
        op.execute("REVOKE ALL PRIVILEGES ON identity.parcel FROM " + role)
    op.execute(f"REVOKE USAGE ON SCHEMA identity, geo FROM {API_RUNTIME_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA identity, geo FROM {INGESTION_RUNTIME_ROLE}")
    op.execute(f"REVOKE SELECT ON public.spatial_ref_sys FROM {INGESTION_RUNTIME_ROLE}")
    op.execute(f"REVOKE SELECT ON geo.opportunity_zone_round FROM {API_RUNTIME_ROLE}")
    op.execute(
        f"REVOKE SELECT ({', '.join(API_OZ_TRACT_SELECT_COLUMNS)}) "
        f"ON geo.opportunity_zone_tract FROM {API_RUNTIME_ROLE}"
    )
    # Table-level REVOKE does not clear PostgreSQL column ACLs. The static importer role must
    # remain inert even if a future migration later re-grants CONNECT or schema USAGE.
    op.execute(
        f"REVOKE UPDATE ({', '.join(OZ_IMPORT_RUN_UPDATE_COLUMNS)}) "
        f"ON geo.opportunity_zone_import_run FROM {OZ_IMPORTER_RUNTIME_ROLE}"
    )
    op.drop_index(
        "ix_geo_oz_membership_parcel_snapshot",
        table_name="opportunity_zone_membership",
        schema="geo",
    )
    op.drop_table("opportunity_zone_membership", schema="geo")
    op.drop_index(
        "ix_geo_oz_membership_build_cohort_started",
        table_name="opportunity_zone_membership_build_run",
        schema="geo",
    )
    op.drop_table("opportunity_zone_membership_build_run", schema="geo")
    op.drop_index(
        "ix_geo_oz_membership_snapshot_cohort_created",
        table_name="opportunity_zone_membership_snapshot",
        schema="geo",
    )
    op.drop_table("opportunity_zone_membership_snapshot", schema="geo")
    op.drop_index(
        "ix_geo_parcel_geometry_geometry_gist",
        table_name="parcel_geometry",
        schema="geo",
    )
    op.drop_index(
        "ix_geo_parcel_geometry_parcel_observed",
        table_name="parcel_geometry",
        schema="geo",
    )
    op.drop_table("parcel_geometry", schema="geo")
    op.drop_table("parcel", schema="identity")
    op.drop_constraint(
        "fk_geo_oz_tract_round_artifact_lineage",
        "opportunity_zone_tract",
        schema="geo",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_geo_oz_round_tract_lineage",
        "opportunity_zone_round",
        schema="geo",
        type_="unique",
    )
    op.drop_constraint(
        "fk_geo_oz_round_artifact_lineage",
        "opportunity_zone_round",
        schema="geo",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_geo_oz_import_run_artifact_lineage",
        "opportunity_zone_import_run",
        schema="geo",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_observation_parcel_geometry_lineage",
        "parcel_observation",
        schema="observation",
        type_="unique",
    )
    op.drop_constraint(
        "fk_observation_parcel_artifact_lineage",
        "parcel_observation",
        schema="observation",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_raw_artifact_lineage_identity",
        "artifact",
        schema="raw",
        type_="unique",
    )
    op.drop_constraint(
        "uq_registry_source_run_lineage_identity",
        "source_run",
        schema="registry",
        type_="unique",
    )
    op.drop_column("parcel_observation", "observed_at", schema="observation")
    op.drop_column("parcel_observation", "local_parcel_id", schema="observation")
    op.drop_column("parcel_observation", "jurisdiction_id", schema="observation")
