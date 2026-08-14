"""Separate application runtime capabilities from the database owner.

The migration creates fixed NOLOGIN capability roles and grants only the permissions used by the
private API and bounded acquisition runtime. Distinct LOGIN principals are provisioned by
``seekandscore.db.roles`` after this migration; credentials and LOGIN roles never belong in
Alembic source.

Revision ID: 20260813_0006
Revises: 20260813_0005
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260813_0006"
down_revision: str | Sequence[str] | None = "20260813_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

API_RUNTIME_ROLE = "seekandscore_api_runtime"
INGESTION_RUNTIME_ROLE = "seekandscore_ingestion_runtime"
RUNTIME_ROLES = (API_RUNTIME_ROLE, INGESTION_RUNTIME_ROLE)
APPLICATION_SCHEMAS = (
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
    # Validate the mutable envelope before a row is accepted. This protects invariants even when
    # SQL reaches the database without passing through the application service.
    op.execute(
        """
        CREATE FUNCTION platform.validate_research_case_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF jsonb_typeof(NEW.payload) IS DISTINCT FROM 'object' THEN
                RAISE EXCEPTION 'research case payload must be an object' USING ERRCODE = '23514';
            END IF;
            IF NEW.payload ->> 'id' IS DISTINCT FROM NEW.id::text
                OR NEW.payload ->> 'organization_id' IS DISTINCT FROM NEW.organization_id::text
                OR NEW.payload ->> 'candidate_id' IS DISTINCT FROM NEW.candidate_id::text
                OR NEW.payload ->> 'status' IS DISTINCT FROM NEW.status
                OR (NEW.payload ->> 'version')::integer IS DISTINCT FROM NEW.version
                OR (NEW.payload ->> 'updated_at')::timestamptz IS DISTINCT FROM NEW.updated_at
                OR NULLIF(NEW.payload ->> 'updated_by', '')::uuid IS NULL
            THEN
                RAISE EXCEPTION 'research case envelope does not match relational columns'
                    USING ERRCODE = '23514';
            END IF;
            IF char_length(COALESCE(NEW.payload ->> 'operator_note', '')) > 4000
                OR char_length(COALESCE(NEW.payload ->> 'next_action', '')) > 500
            THEN
                RAISE EXCEPTION 'research case text exceeds bounded length'
                    USING ERRCODE = '23514';
            END IF;

            IF TG_OP = 'INSERT' THEN
                IF NEW.version <> 1
                    OR (NEW.payload ->> 'created_at')::timestamptz IS DISTINCT FROM NEW.updated_at
                    OR NEW.payload ->> 'created_by' IS DISTINCT FROM NEW.payload ->> 'updated_by'
                THEN
                    RAISE EXCEPTION 'new research case must start at version 1 with one actor/time'
                        USING ERRCODE = '23514';
                END IF;
            ELSE
                IF NEW.id IS DISTINCT FROM OLD.id
                    OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
                    OR NEW.candidate_id IS DISTINCT FROM OLD.candidate_id
                    OR NEW.version <> OLD.version + 1
                THEN
                    RAISE EXCEPTION 'research case identity is immutable and version must advance by 1'
                        USING ERRCODE = '23514';
                END IF;
                IF NEW.payload -> 'region_id' IS DISTINCT FROM OLD.payload -> 'region_id'
                    OR NEW.payload -> 'jurisdiction_id'
                        IS DISTINCT FROM OLD.payload -> 'jurisdiction_id'
                    OR NEW.payload -> 'parcel_id' IS DISTINCT FROM OLD.payload -> 'parcel_id'
                    OR NEW.payload -> 'candidate_read_model_version'
                        IS DISTINCT FROM OLD.payload -> 'candidate_read_model_version'
                    OR NEW.payload -> 'candidate_as_of'
                        IS DISTINCT FROM OLD.payload -> 'candidate_as_of'
                    OR NEW.payload -> 'created_by' IS DISTINCT FROM OLD.payload -> 'created_by'
                    OR NEW.payload -> 'created_at' IS DISTINCT FROM OLD.payload -> 'created_at'
                THEN
                    RAISE EXCEPTION 'research case source identity and creation metadata are immutable'
                        USING ERRCODE = '23514';
                END IF;
                IF NEW.status IS DISTINCT FROM OLD.status
                    AND NOT (
                        (OLD.status = 'watching'
                            AND NEW.status IN ('researching', 'passed', 'archived'))
                        OR (OLD.status = 'researching'
                            AND NEW.status IN ('watching', 'passed', 'archived'))
                        OR (OLD.status = 'passed'
                            AND NEW.status IN ('watching', 'archived'))
                        OR (OLD.status = 'archived' AND NEW.status = 'watching')
                    )
                THEN
                    RAISE EXCEPTION 'invalid research case status transition'
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_case_validate_mutation
        BEFORE INSERT OR UPDATE ON deal.research_case
        FOR EACH ROW EXECUTE FUNCTION platform.validate_research_case_mutation()
        """
    )
    op.execute("REVOKE ALL ON FUNCTION platform.validate_research_case_mutation() FROM PUBLIC")
    # The application role cannot write either append-only ledger. This narrowly scoped
    # SECURITY DEFINER trigger derives both records from the accepted case row so a case mutation
    # cannot bypass or forge its matching revision/audit history.
    op.execute(
        """
        CREATE FUNCTION platform.record_research_case_history()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $$
        BEGIN
            INSERT INTO deal.research_case_revision (
                id,
                organization_id,
                research_case_id,
                version,
                payload,
                recorded_at
            ) VALUES (
                gen_random_uuid(),
                NEW.organization_id,
                NEW.id,
                NEW.version,
                NEW.payload,
                statement_timestamp()
            );
            INSERT INTO platform.audit_event (
                id,
                organization_id,
                actor_id,
                event_type,
                subject_type,
                subject_id,
                recorded_at,
                details
            ) VALUES (
                gen_random_uuid(),
                NEW.organization_id,
                (NEW.payload ->> 'updated_by')::uuid,
                CASE WHEN TG_OP = 'INSERT'
                    THEN 'ResearchCaseCreated'
                    ELSE 'ResearchCaseUpdated'
                END,
                'research_case',
                NEW.id::text,
                statement_timestamp(),
                jsonb_build_object(
                    'candidate_id', NEW.candidate_id::text,
                    'status', NEW.status,
                    'version', NEW.version
                )
            );
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION platform.record_research_case_history() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER trg_research_case_record_history
        AFTER INSERT OR UPDATE ON deal.research_case
        FOR EACH ROW EXECUTE FUNCTION platform.record_research_case_history()
        """
    )

    for role in RUNTIME_ROLES:
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
        # Reconcile an existing role to the same inert capability-role attributes.
        op.execute(
            f"""
            ALTER ROLE {role}
                NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                NOINHERIT NOREPLICATION NOBYPASSRLS
            """
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
                    'GRANT CONNECT ON DATABASE %I TO {role}',
                    current_database()
                );
            END
            $$
            """
        )
    op.execute(
        """
        DO $$
        BEGIN
            -- TEMPORARY comes from PUBLIC by default and is a database-level DDL capability.
            EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
            EXECUTE format('REVOKE CREATE ON DATABASE %I FROM PUBLIC', current_database());
        END
        $$
        """
    )
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")

    # Start from no object privileges. Future migrations must opt the API into each new table.
    for schema in ("public", *APPLICATION_SCHEMAS):
        for role in RUNTIME_ROLES:
            op.execute(f"REVOKE ALL PRIVILEGES ON SCHEMA {schema} FROM {role}")
            op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema} FROM {role}")
            op.execute(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema} FROM {role}")
        op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema} FROM PUBLIC")
        op.execute(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema} FROM PUBLIC")

    op.execute(
        f"GRANT USAGE ON SCHEMA platform, registry, raw, observation, deal TO {API_RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT SELECT ON registry.source_run, raw.artifact, "
        f"observation.parcel_observation, deal.research_case TO {API_RUNTIME_ROLE}"
    )
    op.execute(f"GRANT INSERT ON deal.research_case TO {API_RUNTIME_ROLE}")
    op.execute(
        f"GRANT UPDATE (status, version, payload, updated_at) "
        f"ON deal.research_case TO {API_RUNTIME_ROLE}"
    )
    op.execute(f"GRANT USAGE ON SCHEMA registry, raw, observation TO {INGESTION_RUNTIME_ROLE}")
    op.execute(
        f"GRANT SELECT ON registry.source_run, raw.artifact, "
        f"observation.parcel_observation TO {INGESTION_RUNTIME_ROLE}"
    )
    op.execute(f"GRANT SELECT (id) ON observation.quarantined_record TO {INGESTION_RUNTIME_ROLE}")
    op.execute(
        f"GRANT INSERT ON registry.source_run, raw.artifact, observation.parcel_observation, "
        f"observation.quarantined_record TO {INGESTION_RUNTIME_ROLE}"
    )
    op.execute(f"GRANT UPDATE (payload) ON registry.source_run TO {INGESTION_RUNTIME_ROLE}")


def downgrade() -> None:
    # LOGIN principals may still be members. Leave the cluster role inert rather than making a
    # schema downgrade fail or silently altering external credentials/memberships. The PUBLIC
    # database TEMPORARY/CREATE and public-schema CREATE revocations also remain hardened; broad
    # defaults are never restored implicitly by a downgrade.
    for schema in ("public", *APPLICATION_SCHEMAS):
        for role in RUNTIME_ROLES:
            op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema} FROM {role}")
            op.execute(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema} FROM {role}")
            op.execute(f"REVOKE ALL PRIVILEGES ON SCHEMA {schema} FROM {role}")
    for role in RUNTIME_ROLES:
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
    op.execute("DROP TRIGGER trg_research_case_record_history ON deal.research_case")
    op.execute("DROP FUNCTION platform.record_research_case_history()")
    op.execute("DROP TRIGGER trg_research_case_validate_mutation ON deal.research_case")
    op.execute("DROP FUNCTION platform.validate_research_case_mutation()")
