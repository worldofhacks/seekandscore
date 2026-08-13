"""Bind normalized observations to immutable raw artifacts.

Revision ID: 20260813_0003
Revises: 20260813_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0003"
down_revision: str | Sequence[str] | None = "20260813_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "parcel_observation",
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="observation",
    )
    op.execute(
        """
        UPDATE observation.parcel_observation
        SET artifact_id = (payload ->> 'artifact_id')::uuid
        WHERE artifact_id IS NULL
        """
    )
    op.alter_column(
        "parcel_observation",
        "artifact_id",
        nullable=False,
        schema="observation",
    )
    op.create_index(
        "ix_observation_parcel_artifact",
        "parcel_observation",
        ["artifact_id"],
        schema="observation",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_observation_parcel_artifact",
        table_name="parcel_observation",
        schema="observation",
    )
    op.drop_column("parcel_observation", "artifact_id", schema="observation")
