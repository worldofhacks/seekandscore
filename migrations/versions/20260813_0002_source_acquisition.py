"""Create replay-safe source acquisition ledgers.

Owning contexts: registry, acquisition/raw, observation.
Compatibility: additive; API synthetic mode remains unchanged.
Backfill: none. New rows are created only by explicitly activated source runs.
Downgrade: development only after preserving referenced raw objects.

Revision ID: 20260813_0002
Revises: 20260812_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0002"
down_revision: str | Sequence[str] | None = "20260812_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_definition",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("descriptor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_registry_source_definition"),
        schema="registry",
    )
    op.create_table(
        "source_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_registry_source_run"),
        schema="registry",
    )
    op.create_index(
        "ix_registry_source_run_source_started",
        "source_run",
        ["source_id", sa.text("started_at DESC")],
        schema="registry",
    )
    op.create_table(
        "artifact",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_raw_artifact"),
        sa.UniqueConstraint("source_id", "sha256", name="uq_raw_artifact_source_sha256"),
        schema="raw",
    )
    op.create_index(
        "ix_raw_artifact_source_retrieved",
        "artifact",
        ["source_id", sa.text("retrieved_at DESC")],
        schema="raw",
    )
    op.create_table(
        "parcel_observation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_observation_parcel_observation"),
        sa.UniqueConstraint(
            "source_id",
            "source_record_id",
            "artifact_sha256",
            "parser_version",
            name="uq_observation_parcel_replay_key",
        ),
        schema="observation",
    )
    op.create_table(
        "quarantined_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_observation_quarantined_record"),
        schema="observation",
    )


def downgrade() -> None:
    op.drop_table("quarantined_record", schema="observation")
    op.drop_table("parcel_observation", schema="observation")
    op.drop_index("ix_raw_artifact_source_retrieved", table_name="artifact", schema="raw")
    op.drop_table("artifact", schema="raw")
    op.drop_index(
        "ix_registry_source_run_source_started",
        table_name="source_run",
        schema="registry",
    )
    op.drop_table("source_run", schema="registry")
    op.drop_table("source_definition", schema="registry")
