"""Create organization-scoped research cases and append-only revisions.

Revision ID: 20260813_0005
Revises: 20260813_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0005"
down_revision: str | Sequence[str] | None = "20260813_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_case",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('watching', 'researching', 'passed', 'archived')",
            name="ck_deal_research_case_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_deal_research_case_version"),
        sa.PrimaryKeyConstraint("id", name="pk_deal_research_case"),
        sa.UniqueConstraint(
            "organization_id",
            "candidate_id",
            name="uq_deal_research_case_org_candidate",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_deal_research_case_org_id",
        ),
        schema="deal",
    )
    op.create_index(
        "ix_deal_research_case_org_status_updated",
        "research_case",
        ["organization_id", "status", "updated_at"],
        schema="deal",
    )

    op.create_table(
        "research_case_revision",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "research_case_id"],
            ["deal.research_case.organization_id", "deal.research_case.id"],
            name="fk_deal_research_revision_case",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_deal_research_case_revision"),
        sa.UniqueConstraint(
            "research_case_id",
            "version",
            name="uq_deal_research_revision_case_version",
        ),
        schema="deal",
    )
    op.create_index(
        "ix_deal_research_revision_org_recorded",
        "research_case_revision",
        ["organization_id", "recorded_at"],
        schema="deal",
    )
    op.execute(
        """
        CREATE FUNCTION platform.reject_append_only_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_case_revision_append_only
        BEFORE UPDATE OR DELETE ON deal.research_case_revision
        FOR EACH ROW EXECUTE FUNCTION platform.reject_append_only_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_event_append_only
        BEFORE UPDATE OR DELETE ON platform.audit_event
        FOR EACH ROW EXECUTE FUNCTION platform.reject_append_only_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_audit_event_append_only ON platform.audit_event")
    op.execute("DROP TRIGGER trg_research_case_revision_append_only ON deal.research_case_revision")
    op.execute("DROP FUNCTION platform.reject_append_only_mutation()")
    op.drop_index(
        "ix_deal_research_revision_org_recorded",
        table_name="research_case_revision",
        schema="deal",
    )
    op.drop_table("research_case_revision", schema="deal")
    op.drop_index(
        "ix_deal_research_case_org_status_updated",
        table_name="research_case",
        schema="deal",
    )
    op.drop_table("research_case", schema="deal")
