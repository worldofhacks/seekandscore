"""Create source-pinned 2018 Opportunity Zone geography.

Owning context: geography.
Compatibility: additive; no candidate/read-model behavior changes.
Backfill: none. The importer remains disabled until an exact activation record is supplied.
Downgrade: development only after preserving raw artifacts and import lineage.

Revision ID: 20260813_0004
Revises: 20260813_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0004"
down_revision: str | Sequence[str] | None = "20260813_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class MultiPolygon3857(sa.types.UserDefinedType):  # type: ignore[type-arg]
    cache_ok = True

    def get_col_spec(self, **_kwargs: object) -> str:
        return "geometry(MULTIPOLYGON,3857)"


_STATUS_SQL = (
    "designation_status IN "
    "('eligible','state_nominated','treasury_certified','effective','expired')"
)


def upgrade() -> None:
    op.create_table(
        "opportunity_zone_import_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("activation_id", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("expected_tracts", sa.Integer(), nullable=False),
        sa.Column("imported_tracts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','succeeded','succeeded_unchanged','failed')",
            name="ck_geo_oz_import_run_status",
        ),
        sa.CheckConstraint(
            "length(trim(activation_id)) > 0",
            name="ck_geo_oz_import_run_activation",
        ),
        sa.CheckConstraint(
            "expected_tracts > 0 AND imported_tracts >= 0 AND imported_tracts <= expected_tracts",
            name="ck_geo_oz_import_run_counts",
        ),
        sa.CheckConstraint(
            "source_artifact_sha256 IS NULL OR source_artifact_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_geo_oz_import_run_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"],
            ["raw.artifact.id"],
            name="fk_geo_oz_import_run_artifact",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_geo_oz_import_run"),
        schema="geo",
    )
    op.create_index(
        "ix_geo_oz_import_run_source_started",
        "opportunity_zone_import_run",
        ["source_id", sa.text("started_at DESC")],
        schema="geo",
    )

    op.create_table(
        "opportunity_zone_round",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("round_code", sa.Text(), nullable=False),
        sa.Column("census_vintage", sa.SmallInteger(), nullable=False),
        sa.Column("certification_status", sa.Text(), nullable=False),
        sa.Column("designation_status", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=False),
        sa.Column("tract_intervals_vary", sa.Boolean(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("authority_uri", sa.Text(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_STATUS_SQL, name="ck_geo_oz_round_status"),
        sa.CheckConstraint(
            "certification_status IN "
            "('eligible','state_nominated','treasury_certified','effective','expired')",
            name="ck_geo_oz_round_certification_status",
        ),
        sa.CheckConstraint(
            "effective_from <= effective_to",
            name="ck_geo_oz_round_effective_interval",
        ),
        sa.CheckConstraint(
            "source_artifact_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_geo_oz_round_sha256",
        ),
        sa.CheckConstraint(
            "NOT (round_code = '2027' AND designation_status = 'effective')",
            name="ck_geo_oz_round_2027_not_effective",
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"],
            ["raw.artifact.id"],
            name="fk_geo_oz_round_artifact",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_geo_oz_round"),
        sa.UniqueConstraint(
            "id",
            "source_artifact_id",
            name="uq_geo_oz_round_artifact",
        ),
        schema="geo",
    )

    op.create_table(
        "opportunity_zone_tract",
        sa.Column("round_id", sa.Text(), nullable=False),
        sa.Column("tract_geoid", sa.String(length=11), nullable=False),
        sa.Column("census_vintage", sa.SmallInteger(), nullable=False),
        sa.Column("certification_status", sa.Text(), nullable=False),
        sa.Column("designation_status", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_from_precision", sa.Text(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=False),
        sa.Column("state_name", sa.Text(), nullable=False),
        sa.Column("county_name", sa.Text(), nullable=False),
        sa.Column("source_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("geometry", MultiPolygon3857(), nullable=False),
        sa.Column("geometry_was_repaired", sa.Boolean(), nullable=False),
        sa.Column("geometry_repair_method", sa.Text(), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tract_geoid ~ '^[0-9]{11}$'",
            name="ck_geo_oz_tract_geoid",
        ),
        sa.CheckConstraint(_STATUS_SQL, name="ck_geo_oz_tract_status"),
        sa.CheckConstraint(
            "certification_status IN "
            "('eligible','state_nominated','treasury_certified','effective','expired')",
            name="ck_geo_oz_tract_certification_status",
        ),
        sa.CheckConstraint(
            "effective_from_precision IN ('exact','year')",
            name="ck_geo_oz_tract_effective_precision",
        ),
        sa.CheckConstraint(
            "effective_from <= effective_to",
            name="ck_geo_oz_tract_effective_interval",
        ),
        sa.CheckConstraint(
            "source_artifact_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_geo_oz_tract_sha256",
        ),
        sa.CheckConstraint(
            "ST_IsValid(geometry) AND NOT ST_IsEmpty(geometry)",
            name="ck_geo_oz_tract_valid_geometry",
        ),
        sa.CheckConstraint(
            "(geometry_was_repaired AND geometry_repair_method IS NOT NULL) OR "
            "(NOT geometry_was_repaired AND geometry_repair_method IS NULL)",
            name="ck_geo_oz_tract_repair_lineage",
        ),
        sa.ForeignKeyConstraint(
            ["round_id", "source_artifact_id"],
            ["geo.opportunity_zone_round.id", "geo.opportunity_zone_round.source_artifact_id"],
            name="fk_geo_oz_tract_round_artifact",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "round_id",
            "tract_geoid",
            name="pk_geo_oz_tract",
        ),
        schema="geo",
    )
    op.create_index(
        "ix_geo_oz_tract_geoid",
        "opportunity_zone_tract",
        ["tract_geoid"],
        schema="geo",
    )
    op.create_index(
        "ix_geo_oz_tract_geometry_gist",
        "opportunity_zone_tract",
        ["geometry"],
        postgresql_using="gist",
        schema="geo",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_geo_oz_tract_geometry_gist",
        table_name="opportunity_zone_tract",
        schema="geo",
    )
    op.drop_index(
        "ix_geo_oz_tract_geoid",
        table_name="opportunity_zone_tract",
        schema="geo",
    )
    op.drop_table("opportunity_zone_tract", schema="geo")
    op.drop_table("opportunity_zone_round", schema="geo")
    op.drop_index(
        "ix_geo_oz_import_run_source_started",
        table_name="opportunity_zone_import_run",
        schema="geo",
    )
    op.drop_table("opportunity_zone_import_run", schema="geo")
