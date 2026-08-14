"""Create foundational context schemas and platform audit table.

Owning context: platform (schemas are registered for all foundational contexts).
Compatibility: additive; the audit table is unused by earlier releases.
Downgrade: available for development only. Production uses a forward fix after use.

Revision ID: 20260812_0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260812_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS = (
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
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    for schema in SCHEMAS:
        op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    op.create_table(
        "audit_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_platform_audit_event"),
        schema="platform",
    )
    op.create_index(
        "ix_platform_audit_event_org_recorded_at",
        "audit_event",
        ["organization_id", "recorded_at"],
        unique=False,
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_audit_event_org_recorded_at",
        table_name="audit_event",
        schema="platform",
    )
    op.drop_table("audit_event", schema="platform")
    for schema in reversed(SCHEMAS):
        op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}"'))
