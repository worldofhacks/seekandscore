"""Provision and audit least-privilege application database principals."""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import sqlalchemy as sa
from psycopg import ClientCursor
from psycopg import Connection as PsycopgConnection
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

API_RUNTIME_CAPABILITY_ROLE = "seekandscore_api_runtime"
INGESTION_RUNTIME_CAPABILITY_ROLE = "seekandscore_ingestion_runtime"
OZ_IMPORTER_RUNTIME_CAPABILITY_ROLE = "seekandscore_oz_importer_runtime"
OZ_MEMBERSHIP_RUNTIME_CAPABILITY_ROLE = "seekandscore_oz_membership_runtime"
DEFAULT_API_LOGIN_ROLE = "seekandscore_api"
DEFAULT_INGESTION_LOGIN_ROLE = "seekandscore_ingestion"
DEFAULT_OZ_IMPORTER_LOGIN_ROLE = "seekandscore_oz_importer"
DEFAULT_OZ_MEMBERSHIP_LOGIN_ROLE = "seekandscore_oz_membership"
ROLE_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]{2,62}\Z")
PASSWORD_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,128}\Z")
# pg_trigger.tgtype bitmask: ROW(1) | BEFORE(2) | INSERT(4) | UPDATE(16).
POSTGRES_TRIGGER_BEFORE_ROW_INSERT_UPDATE = 23

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


class DatabaseRoleConfigurationError(ValueError):
    """Raised when role provisioning inputs are absent or unsafe."""


class DatabaseRoleAuditError(RuntimeError):
    """Raised when the runtime connection has more or fewer privileges than intended."""


@dataclass(frozen=True)
class DatabaseRoleAudit:
    current_user: str
    capability_role: str
    checked_relations: int


@dataclass(frozen=True)
class RuntimeRoleContract:
    capability_role: str
    default_login_role: str
    schema_usage: frozenset[str]
    select_tables: frozenset[str]
    select_columns: frozenset[str]
    insert_tables: frozenset[str]
    update_columns: frozenset[str]
    verifies_research_history: bool = False
    allows_temporary: bool = False
    required_triggers: tuple[tuple[str, str, str, str, str, int], ...] = ()


API_ROLE_CONTRACT = RuntimeRoleContract(
    capability_role=API_RUNTIME_CAPABILITY_ROLE,
    default_login_role=DEFAULT_API_LOGIN_ROLE,
    schema_usage=frozenset(
        {"public", "platform", "registry", "raw", "observation", "identity", "geo", "deal"}
    ),
    select_tables=frozenset(
        {
            "registry.source_run",
            "raw.artifact",
            "observation.parcel_observation",
            "identity.parcel",
            "geo.opportunity_zone_round",
            "geo.opportunity_zone_membership_snapshot",
            "geo.opportunity_zone_membership_build_run",
            "geo.opportunity_zone_membership",
            "deal.research_case",
        }
    ),
    select_columns=frozenset(
        {
            "geo.parcel_geometry.observation_id",
            "geo.parcel_geometry.parcel_id",
            "geo.parcel_geometry.source_id",
            "geo.parcel_geometry.source_record_id",
            "geo.parcel_geometry.source_artifact_id",
            "geo.parcel_geometry.source_artifact_sha256",
            "geo.parcel_geometry.parser_version",
            "geo.parcel_geometry.source_srid",
            "geo.parcel_geometry.geometry_was_repaired",
            "geo.parcel_geometry.geometry_repair_method",
            "geo.parcel_geometry.observed_at",
            "geo.opportunity_zone_tract.round_id",
            "geo.opportunity_zone_tract.tract_geoid",
            "geo.opportunity_zone_tract.census_vintage",
            "geo.opportunity_zone_tract.certification_status",
            "geo.opportunity_zone_tract.designation_status",
            "geo.opportunity_zone_tract.effective_from",
            "geo.opportunity_zone_tract.effective_from_precision",
            "geo.opportunity_zone_tract.effective_to",
            "geo.opportunity_zone_tract.state_name",
            "geo.opportunity_zone_tract.county_name",
            "geo.opportunity_zone_tract.source_artifact_id",
            "geo.opportunity_zone_tract.source_artifact_sha256",
            "geo.opportunity_zone_tract.geometry_was_repaired",
            "geo.opportunity_zone_tract.geometry_repair_method",
            "geo.opportunity_zone_tract.loaded_at",
        }
    ),
    insert_tables=frozenset({"deal.research_case"}),
    update_columns=frozenset(
        {
            "deal.research_case.status",
            "deal.research_case.version",
            "deal.research_case.payload",
            "deal.research_case.updated_at",
        }
    ),
    verifies_research_history=True,
)

INGESTION_ROLE_CONTRACT = RuntimeRoleContract(
    capability_role=INGESTION_RUNTIME_CAPABILITY_ROLE,
    default_login_role=DEFAULT_INGESTION_LOGIN_ROLE,
    schema_usage=frozenset({"public", "registry", "raw", "observation", "identity", "geo"}),
    select_tables=frozenset(
        {
            "registry.source_run",
            "raw.artifact",
            "observation.parcel_observation",
            "public.spatial_ref_sys",
            "identity.parcel",
            "geo.parcel_geometry",
        }
    ),
    select_columns=frozenset({"observation.quarantined_record.id"}),
    insert_tables=frozenset(
        {
            "registry.source_run",
            "raw.artifact",
            "observation.parcel_observation",
            "observation.quarantined_record",
            "identity.parcel",
            "geo.parcel_geometry",
        }
    ),
    update_columns=frozenset({"registry.source_run.payload"}),
)

OZ_IMPORTER_ROLE_CONTRACT = RuntimeRoleContract(
    capability_role=OZ_IMPORTER_RUNTIME_CAPABILITY_ROLE,
    default_login_role=DEFAULT_OZ_IMPORTER_LOGIN_ROLE,
    schema_usage=frozenset({"public", "registry", "raw", "geo"}),
    select_tables=frozenset(
        {
            "registry.source_definition",
            "raw.artifact",
            "geo.opportunity_zone_import_run",
            "geo.opportunity_zone_round",
            "geo.opportunity_zone_tract",
        }
    ),
    select_columns=frozenset(),
    insert_tables=frozenset(
        {
            "registry.source_definition",
            "raw.artifact",
            "geo.opportunity_zone_import_run",
            "geo.opportunity_zone_round",
            "geo.opportunity_zone_tract",
        }
    ),
    update_columns=frozenset(
        {
            "geo.opportunity_zone_import_run.status",
            "geo.opportunity_zone_import_run.completed_at",
            "geo.opportunity_zone_import_run.source_artifact_id",
            "geo.opportunity_zone_import_run.source_artifact_sha256",
            "geo.opportunity_zone_import_run.imported_tracts",
            "geo.opportunity_zone_import_run.error_code",
            "geo.opportunity_zone_import_run.error_detail",
        }
    ),
    allows_temporary=True,
    required_triggers=(
        (
            "geo",
            "opportunity_zone_import_run",
            "trg_oz_import_run_validate_transition",
            "geo",
            "validate_oz_import_run_transition",
            POSTGRES_TRIGGER_BEFORE_ROW_INSERT_UPDATE,
        ),
    ),
)

OZ_MEMBERSHIP_ROLE_CONTRACT = RuntimeRoleContract(
    capability_role=OZ_MEMBERSHIP_RUNTIME_CAPABILITY_ROLE,
    default_login_role=DEFAULT_OZ_MEMBERSHIP_LOGIN_ROLE,
    schema_usage=frozenset({"public", "registry", "observation", "identity", "geo"}),
    select_tables=frozenset(
        {
            "registry.source_run",
            "observation.parcel_observation",
            "identity.parcel",
            "geo.parcel_geometry",
            "geo.opportunity_zone_import_run",
            "geo.opportunity_zone_round",
            "geo.opportunity_zone_tract",
            "geo.opportunity_zone_membership_snapshot",
            "geo.opportunity_zone_membership_build_run",
            "geo.opportunity_zone_membership",
        }
    ),
    select_columns=frozenset(),
    insert_tables=frozenset(
        {
            "geo.opportunity_zone_membership_snapshot",
            "geo.opportunity_zone_membership_build_run",
            "geo.opportunity_zone_membership",
        }
    ),
    update_columns=frozenset(
        {
            "geo.opportunity_zone_membership_build_run.status",
            "geo.opportunity_zone_membership_build_run.completed_at",
            "geo.opportunity_zone_membership_build_run.snapshot_id",
            "geo.opportunity_zone_membership_build_run.evaluated_parcels",
            "geo.opportunity_zone_membership_build_run.inside_count",
            "geo.opportunity_zone_membership_build_run.outside_count",
            "geo.opportunity_zone_membership_build_run.boundary_review_count",
            "geo.opportunity_zone_membership_build_run.missing_geometry_count",
            "geo.opportunity_zone_membership_build_run.error_code",
            "geo.opportunity_zone_membership_build_run.error_detail",
        }
    ),
    allows_temporary=True,
    required_triggers=(
        (
            "geo",
            "opportunity_zone_membership_build_run",
            "trg_oz_membership_build_validate_transition",
            "geo",
            "validate_oz_membership_build_transition",
            POSTGRES_TRIGGER_BEFORE_ROW_INSERT_UPDATE,
        ),
        (
            "geo",
            "opportunity_zone_membership",
            "trg_oz_membership_validate_geometry_lineage",
            "geo",
            "validate_oz_membership_geometry_lineage",
            POSTGRES_TRIGGER_BEFORE_ROW_INSERT_UPDATE,
        ),
    ),
)


def _validated_role_name(value: str, *, capability_role: str) -> str:
    if not ROLE_NAME_PATTERN.fullmatch(value):
        raise DatabaseRoleConfigurationError(
            "runtime login role must be a 3-63 character lowercase Postgres identifier"
        )
    if value == capability_role:
        raise DatabaseRoleConfigurationError("login and capability roles must be distinct")
    return value


def _validated_password(value: str) -> str:
    if not PASSWORD_PATTERN.fullmatch(value):
        raise DatabaseRoleConfigurationError(
            "runtime database password must be 32-128 URL-safe characters (A-Z, a-z, 0-9, _, -)"
        )
    return value


def _engine(database_url: str) -> Engine:
    return sa.create_engine(
        database_url,
        pool_pre_ping=True,
        poolclass=NullPool,
        hide_parameters=True,
    )


def _quoted(connection: Connection, identifier: str) -> str:
    return connection.dialect.identifier_preparer.quote(identifier)


def _set_role_password(connection: Connection, quoted_login: str, password: str) -> None:
    """Use Psycopg client-side binding and never propagate a password-bearing exception."""

    statement = (
        f"ALTER ROLE {quoted_login} LOGIN INHERIT NOSUPERUSER NOCREATEDB "
        "NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 20 PASSWORD %s"
    )
    try:
        raw_connection = cast(PsycopgConnection[Any], connection.connection.driver_connection)
        with ClientCursor(raw_connection) as cursor:
            cursor.execute(statement, (password,))
    except Exception:
        raise DatabaseRoleConfigurationError(
            "could not securely set the runtime database password"
        ) from None


def _owned_objects(connection: Connection, role_name: str) -> tuple[str, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT object_kind || ':' || object_name
            FROM (
                SELECT 'database' AS object_kind, datname AS object_name
                FROM pg_database
                WHERE datdba = (SELECT oid FROM pg_roles WHERE rolname = :role_name)
                UNION ALL
                SELECT 'schema', nspname
                FROM pg_namespace
                WHERE nspowner = (SELECT oid FROM pg_roles WHERE rolname = :role_name)
                UNION ALL
                SELECT 'relation', format('%I.%I', n.nspname, c.relname)
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relowner = (SELECT oid FROM pg_roles WHERE rolname = :role_name)
                UNION ALL
                SELECT 'routine', format('%I.%I', n.nspname, p.proname)
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE p.proowner = (SELECT oid FROM pg_roles WHERE rolname = :role_name)
            ) owned
            ORDER BY object_kind, object_name
            """
        ),
        {"role_name": role_name},
    ).scalars()
    return tuple(str(item) for item in rows)


def provision_runtime_role(
    owner_database_url: str,
    *,
    contract: RuntimeRoleContract,
    login_role: str,
    password: str,
) -> str:
    """Create or reconcile one LOGIN principal as a member of the fixed capability role."""

    login_role = _validated_role_name(login_role, capability_role=contract.capability_role)
    password = _validated_password(password)
    engine = _engine(owner_database_url)
    try:
        with engine.begin() as connection:
            current_user = str(connection.scalar(sa.text("SELECT current_user")))
            if login_role == current_user:
                raise DatabaseRoleConfigurationError(
                    "runtime login must not be the migration/database-owner principal"
                )
            owner_attributes = connection.execute(
                sa.text(
                    """
                    SELECT rolsuper, rolcreaterole
                    FROM pg_roles
                    WHERE rolname = current_user
                    """
                )
            ).one()
            if not bool(owner_attributes.rolsuper or owner_attributes.rolcreaterole):
                raise DatabaseRoleConfigurationError(
                    "migration principal must have CREATEROLE to provision the runtime login"
                )
            capability = (
                connection.execute(
                    sa.text(
                        """
                    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication,
                           rolbypassrls
                    FROM pg_roles
                    WHERE rolname = :role_name
                    """
                    ),
                    {"role_name": contract.capability_role},
                )
                .mappings()
                .one_or_none()
            )
            if capability is None:
                raise DatabaseRoleConfigurationError(
                    "runtime capability role is absent; run Alembic upgrade before provisioning"
                )
            if any(bool(capability[key]) for key in capability):
                raise DatabaseRoleConfigurationError(
                    "runtime capability role has unsafe attributes"
                )

            role_exists = bool(
                connection.scalar(
                    sa.text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role_name)"),
                    {"role_name": login_role},
                )
            )
            if role_exists:
                owned = _owned_objects(connection, login_role)
                if owned:
                    raise DatabaseRoleConfigurationError(
                        "existing runtime login owns objects and cannot be safely reconciled: "
                        + ", ".join(owned[:5])
                    )
            quoted_login = _quoted(connection, login_role)
            quoted_capability = _quoted(connection, contract.capability_role)
            if not role_exists:
                connection.exec_driver_sql(f"CREATE ROLE {quoted_login} LOGIN")

            _set_role_password(connection, quoted_login, password)
            connection.exec_driver_sql(
                f"ALTER ROLE {quoted_login} SET search_path TO pg_catalog, public"
            )
            connection.exec_driver_sql(f"ALTER ROLE {quoted_login} SET statement_timeout TO '15s'")
            connection.exec_driver_sql(f"ALTER ROLE {quoted_login} SET lock_timeout TO '5s'")
            connection.exec_driver_sql(
                f"ALTER ROLE {quoted_login} SET idle_in_transaction_session_timeout TO '15s'"
            )

            memberships = connection.execute(
                sa.text(
                    """
                    SELECT parent.rolname
                    FROM pg_auth_members membership
                    JOIN pg_roles parent ON parent.oid = membership.roleid
                    JOIN pg_roles member ON member.oid = membership.member
                    WHERE member.rolname = :role_name
                    """
                ),
                {"role_name": login_role},
            ).scalars()
            for parent_role in memberships:
                if parent_role != contract.capability_role:
                    connection.exec_driver_sql(
                        f"REVOKE {_quoted(connection, str(parent_role))} FROM {quoted_login}"
                    )

            database_name = str(connection.scalar(sa.text("SELECT current_database()")))
            connection.exec_driver_sql(
                f"REVOKE ALL PRIVILEGES ON DATABASE {_quoted(connection, database_name)} "
                f"FROM {quoted_login}"
            )
            for schema in ("public", *APPLICATION_SCHEMAS):
                quoted_schema = _quoted(connection, schema)
                connection.exec_driver_sql(
                    f"REVOKE ALL PRIVILEGES ON SCHEMA {quoted_schema} FROM {quoted_login}"
                )
                connection.exec_driver_sql(
                    f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {quoted_schema} "
                    f"FROM {quoted_login}"
                )
                connection.exec_driver_sql(
                    f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {quoted_schema} "
                    f"FROM {quoted_login}"
                )
                connection.exec_driver_sql(
                    f"REVOKE ALL PRIVILEGES ON ALL ROUTINES IN SCHEMA {quoted_schema} "
                    f"FROM {quoted_login}"
                )
            connection.exec_driver_sql(f"GRANT {quoted_capability} TO {quoted_login}")
    finally:
        engine.dispose()
    return login_role


def provision_api_runtime(
    owner_database_url: str,
    *,
    login_role: str = DEFAULT_API_LOGIN_ROLE,
    password: str,
) -> str:
    return provision_runtime_role(
        owner_database_url,
        contract=API_ROLE_CONTRACT,
        login_role=login_role,
        password=password,
    )


def provision_ingestion_runtime(
    owner_database_url: str,
    *,
    login_role: str = DEFAULT_INGESTION_LOGIN_ROLE,
    password: str,
) -> str:
    return provision_runtime_role(
        owner_database_url,
        contract=INGESTION_ROLE_CONTRACT,
        login_role=login_role,
        password=password,
    )


def provision_oz_importer_runtime(
    owner_database_url: str,
    *,
    login_role: str = DEFAULT_OZ_IMPORTER_LOGIN_ROLE,
    password: str,
) -> str:
    return provision_runtime_role(
        owner_database_url,
        contract=OZ_IMPORTER_ROLE_CONTRACT,
        login_role=login_role,
        password=password,
    )


def provision_oz_membership_runtime(
    owner_database_url: str,
    *,
    login_role: str = DEFAULT_OZ_MEMBERSHIP_LOGIN_ROLE,
    password: str,
) -> str:
    return provision_runtime_role(
        owner_database_url,
        contract=OZ_MEMBERSHIP_ROLE_CONTRACT,
        login_role=login_role,
        password=password,
    )


def _runtime_relation_privileges(connection: Connection) -> list[Mapping[str, object]]:
    rows = connection.execute(
        sa.text(
            """
                SELECT
                    format('%I.%I', n.nspname, c.relname) AS relation_name,
                    has_table_privilege(c.oid, 'SELECT') AS can_select,
                    has_table_privilege(c.oid, 'INSERT') AS can_insert,
                    has_table_privilege(c.oid, 'UPDATE') AS can_update,
                    has_table_privilege(c.oid, 'DELETE') AS can_delete,
                    has_table_privilege(c.oid, 'TRUNCATE') AS can_truncate,
                    has_table_privilege(c.oid, 'REFERENCES') AS can_reference,
                    has_table_privilege(c.oid, 'TRIGGER') AS can_trigger
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = ANY(:schemas)
                  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
                ORDER BY n.nspname, c.relname
                """
        ),
        {"schemas": ["public", *APPLICATION_SCHEMAS]},
    ).mappings()
    return [cast(Mapping[str, object], row) for row in rows]


def audit_runtime_role(
    runtime_database_url: str,
    *,
    contract: RuntimeRoleContract,
    expected_login_role: str,
) -> DatabaseRoleAudit:
    """Fail unless a runtime connection matches its exact privilege contract."""

    expected_login_role = _validated_role_name(
        expected_login_role,
        capability_role=contract.capability_role,
    )
    engine = _engine(runtime_database_url)
    failures: list[str] = []
    try:
        with engine.connect() as connection:
            identity = (
                connection.execute(
                    sa.text(
                        """
                    SELECT current_user, session_user, rolcanlogin, rolinherit, rolsuper,
                           rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
                    FROM pg_roles
                    WHERE rolname = current_user
                    """
                    )
                )
                .mappings()
                .one()
            )
            current_user = str(identity["current_user"])
            if current_user != expected_login_role or identity["session_user"] != current_user:
                failures.append("runtime connection does not authenticate as the expected login")
            for attribute in (
                "rolsuper",
                "rolcreatedb",
                "rolcreaterole",
                "rolreplication",
                "rolbypassrls",
            ):
                if bool(identity[attribute]):
                    failures.append(f"runtime login has forbidden {attribute} capability")
            if not bool(identity["rolcanlogin"] and identity["rolinherit"]):
                failures.append("runtime principal must be an inheriting LOGIN role")

            memberships = {
                str(item)
                for item in connection.execute(
                    sa.text(
                        """
                        SELECT rolname
                        FROM pg_roles
                        WHERE rolname <> current_user
                          AND pg_has_role(current_user, oid, 'MEMBER')
                        """
                    )
                ).scalars()
            }
            if memberships != {contract.capability_role}:
                failures.append(
                    "runtime login has unexpected role memberships: "
                    + ", ".join(sorted(memberships))
                )

            database_privileges = (
                connection.execute(
                    sa.text(
                        """
                    SELECT
                        has_database_privilege(current_database(), 'CONNECT') AS can_connect,
                        has_database_privilege(current_database(), 'CREATE') AS can_create,
                        has_database_privilege(current_database(), 'TEMPORARY') AS can_temp
                    """
                    )
                )
                .mappings()
                .one()
            )
            if not bool(database_privileges["can_connect"]):
                failures.append("runtime login cannot CONNECT to the application database")
            if bool(database_privileges["can_create"]):
                failures.append("runtime login has database CREATE capability")
            if bool(database_privileges["can_temp"]) != contract.allows_temporary:
                failures.append("runtime TEMPORARY privilege differs from the exact contract")

            schema_rows = connection.execute(
                sa.text(
                    """
                    SELECT nspname,
                           has_schema_privilege(oid, 'USAGE') AS can_use,
                           has_schema_privilege(oid, 'CREATE') AS can_create
                    FROM pg_namespace
                    WHERE nspname = ANY(:schemas)
                    ORDER BY nspname
                    """
                ),
                {"schemas": ["public", *APPLICATION_SCHEMAS]},
            ).mappings()
            for row in schema_rows:
                schema = str(row["nspname"])
                if bool(row["can_create"]):
                    failures.append(f"runtime login can CREATE in schema {schema}")
                if bool(row["can_use"]) != (schema in contract.schema_usage):
                    failures.append(f"runtime schema USAGE differs from contract for {schema}")

            owned = connection.execute(
                sa.text(
                    """
                    SELECT format('%I.%I', n.nspname, c.relname)
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = ANY(:schemas)
                      AND pg_has_role(current_user, c.relowner, 'MEMBER')
                    UNION ALL
                    SELECT 'database:' || datname
                    FROM pg_database
                    WHERE datname = current_database()
                      AND pg_has_role(current_user, datdba, 'MEMBER')
                    """
                ),
                {"schemas": ["public", *APPLICATION_SCHEMAS]},
            ).scalars()
            owned_objects = tuple(str(item) for item in owned)
            if owned_objects:
                failures.append(
                    "runtime login owns or can assume an owner of database objects: "
                    + ", ".join(owned_objects[:5])
                )

            relations = _runtime_relation_privileges(connection)
            for relation_row in relations:
                relation = str(relation_row["relation_name"])
                if bool(relation_row["can_select"]) != (relation in contract.select_tables):
                    failures.append(f"unexpected SELECT privilege state for {relation}")
                if bool(relation_row["can_insert"]) != (relation in contract.insert_tables):
                    failures.append(f"unexpected INSERT privilege state for {relation}")
                if bool(relation_row["can_update"]):
                    failures.append(f"runtime has table-wide UPDATE on {relation}")
                for privilege in ("can_delete", "can_truncate", "can_reference", "can_trigger"):
                    if bool(relation_row[privilege]):
                        failures.append(
                            f"runtime has forbidden {privilege[4:].upper()} on {relation}"
                        )

            column_privileges = connection.execute(
                sa.text(
                    """
                    SELECT format('%I.%I.%I', n.nspname, c.relname, a.attname) AS column_name,
                           has_column_privilege(c.oid, a.attnum, 'SELECT')
                               AND NOT has_table_privilege(c.oid, 'SELECT') AS column_select,
                           has_column_privilege(c.oid, a.attnum, 'UPDATE') AS column_update
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    JOIN pg_attribute a ON a.attrelid = c.oid
                    WHERE n.nspname = ANY(:schemas)
                      AND c.relkind IN ('r', 'p')
                      AND a.attnum > 0
                      AND NOT a.attisdropped
                    """
                ),
                {"schemas": ["public", *APPLICATION_SCHEMAS]},
            ).mappings()
            select_columns: set[str] = set()
            update_columns: set[str] = set()
            for column in column_privileges:
                column_name = str(column["column_name"])
                if bool(column["column_select"]):
                    select_columns.add(column_name)
                if bool(column["column_update"]):
                    update_columns.add(column_name)
            if select_columns != contract.select_columns:
                failures.append("runtime column SELECT privileges differ from the exact contract")
            if update_columns != contract.update_columns:
                failures.append("runtime column UPDATE privileges differ from the exact contract")

            sequence_privilege = bool(
                connection.scalar(
                    sa.text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM pg_class c
                            JOIN pg_namespace n ON n.oid = c.relnamespace
                            WHERE n.nspname = ANY(:schemas)
                              AND c.relkind = 'S'
                              AND (
                                  has_sequence_privilege(c.oid, 'USAGE')
                                  OR has_sequence_privilege(c.oid, 'UPDATE')
                              )
                        )
                        """
                    ),
                    {"schemas": list(APPLICATION_SCHEMAS)},
                )
            )
            if sequence_privilege:
                failures.append("runtime login has sequence mutation privileges")

            if contract.verifies_research_history:
                trigger_contract = (
                    connection.execute(
                        sa.text(
                            """
                        SELECT
                            bool_and(t.tgenabled = 'O') AS all_enabled,
                            count(*) FILTER (
                                WHERE t.tgname = 'trg_research_case_validate_mutation'
                            ) AS validation_count,
                            count(*) FILTER (
                                WHERE t.tgname = 'trg_research_case_record_history'
                            ) AS history_count,
                            bool_and(
                                CASE WHEN t.tgname = 'trg_research_case_record_history'
                                    THEN p.prosecdef
                                        AND p.proconfig @> ARRAY['search_path=pg_catalog']::text[]
                                        AND NOT has_function_privilege(
                                            current_user, p.oid, 'EXECUTE'
                                        )
                                    ELSE true
                                END
                            ) AS history_function_safe
                        FROM pg_trigger t
                        JOIN pg_class c ON c.oid = t.tgrelid
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        JOIN pg_proc p ON p.oid = t.tgfoid
                        WHERE n.nspname = 'deal'
                          AND c.relname = 'research_case'
                          AND NOT t.tgisinternal
                        """
                        )
                    )
                    .mappings()
                    .one()
                )
                if (
                    not bool(trigger_contract["all_enabled"])
                    or trigger_contract["validation_count"] != 1
                    or trigger_contract["history_count"] != 1
                    or not bool(trigger_contract["history_function_safe"])
                ):
                    failures.append(
                        "research-case validation/history trigger contract is not active"
                    )

            for (
                schema_name,
                table_name,
                trigger_name,
                function_schema,
                function_name,
                trigger_type,
            ) in contract.required_triggers:
                required_trigger = (
                    connection.execute(
                        sa.text(
                            """
                            SELECT count(*) AS trigger_count,
                                   bool_and(
                                       t.tgenabled = 'O'
                                       AND t.tgtype = :trigger_type
                                       AND t.tgattr = ''::int2vector
                                       AND t.tgnargs = 0
                                       AND t.tgqual IS NULL
                                       AND pn.nspname = :function_schema
                                       AND p.proname = :function_name
                                       AND p.prosecdef
                                       AND p.proconfig @>
                                           ARRAY['search_path=pg_catalog']::text[]
                                       AND NOT has_function_privilege(
                                           current_user, p.oid, 'EXECUTE'
                                       )
                                   ) AS trigger_safe
                            FROM pg_trigger AS t
                            JOIN pg_class AS c ON c.oid = t.tgrelid
                            JOIN pg_namespace AS n ON n.oid = c.relnamespace
                            JOIN pg_proc AS p ON p.oid = t.tgfoid
                            JOIN pg_namespace AS pn ON pn.oid = p.pronamespace
                            WHERE n.nspname = :schema_name
                              AND c.relname = :table_name
                              AND t.tgname = :trigger_name
                              AND NOT t.tgisinternal
                            """
                        ),
                        {
                            "schema_name": schema_name,
                            "table_name": table_name,
                            "trigger_name": trigger_name,
                            "function_schema": function_schema,
                            "function_name": function_name,
                            "trigger_type": trigger_type,
                        },
                    )
                    .mappings()
                    .one()
                )
                if required_trigger["trigger_count"] != 1 or not bool(
                    required_trigger["trigger_safe"]
                ):
                    failures.append(
                        f"{schema_name}.{table_name} required trigger contract is not active"
                    )
    except sa.exc.SQLAlchemyError as error:
        raise DatabaseRoleAuditError("runtime role audit could not query PostgreSQL") from error
    finally:
        engine.dispose()

    if failures:
        raise DatabaseRoleAuditError("; ".join(failures))
    return DatabaseRoleAudit(
        current_user=current_user,
        capability_role=contract.capability_role,
        checked_relations=len(relations),
    )


def audit_api_runtime(
    runtime_database_url: str,
    *,
    expected_login_role: str = DEFAULT_API_LOGIN_ROLE,
) -> DatabaseRoleAudit:
    return audit_runtime_role(
        runtime_database_url,
        contract=API_ROLE_CONTRACT,
        expected_login_role=expected_login_role,
    )


def audit_ingestion_runtime(
    runtime_database_url: str,
    *,
    expected_login_role: str = DEFAULT_INGESTION_LOGIN_ROLE,
) -> DatabaseRoleAudit:
    return audit_runtime_role(
        runtime_database_url,
        contract=INGESTION_ROLE_CONTRACT,
        expected_login_role=expected_login_role,
    )


def audit_oz_importer_runtime(
    runtime_database_url: str,
    *,
    expected_login_role: str = DEFAULT_OZ_IMPORTER_LOGIN_ROLE,
) -> DatabaseRoleAudit:
    return audit_runtime_role(
        runtime_database_url,
        contract=OZ_IMPORTER_ROLE_CONTRACT,
        expected_login_role=expected_login_role,
    )


def audit_oz_membership_runtime(
    runtime_database_url: str,
    *,
    expected_login_role: str = DEFAULT_OZ_MEMBERSHIP_LOGIN_ROLE,
) -> DatabaseRoleAudit:
    return audit_runtime_role(
        runtime_database_url,
        contract=OZ_MEMBERSHIP_ROLE_CONTRACT,
        expected_login_role=expected_login_role,
    )


def _environment_value(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "")
    if not value:
        raise DatabaseRoleConfigurationError(f"{name} is required")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage restricted application database logins")
    parser.add_argument(
        "command",
        choices=(
            "provision-api-runtime",
            "audit-api-runtime",
            "provision-ingestion-runtime",
            "audit-ingestion-runtime",
            "provision-oz-importer-runtime",
            "audit-oz-importer-runtime",
            "provision-oz-membership-runtime",
            "audit-oz-membership-runtime",
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    environment = os.environ
    try:
        if args.command == "provision-api-runtime":
            login_role = environment.get("API_DATABASE_LOGIN_ROLE", DEFAULT_API_LOGIN_ROLE)
            provision_api_runtime(
                _environment_value(environment, "MIGRATION_DATABASE_URL"),
                login_role=login_role,
                password=_environment_value(environment, "API_DATABASE_PASSWORD"),
            )
            print(f"Provisioned restricted database login {login_role}.")
        elif args.command == "audit-api-runtime":
            login_role = environment.get("API_DATABASE_LOGIN_ROLE", DEFAULT_API_LOGIN_ROLE)
            result = audit_api_runtime(
                _environment_value(environment, "DATABASE_URL"),
                expected_login_role=login_role,
            )
            print(
                f"Database role audit passed for {result.current_user} "
                f"across {result.checked_relations} application relations."
            )
        elif args.command == "provision-ingestion-runtime":
            login_role = environment.get(
                "INGESTION_DATABASE_LOGIN_ROLE", DEFAULT_INGESTION_LOGIN_ROLE
            )
            provision_ingestion_runtime(
                _environment_value(environment, "MIGRATION_DATABASE_URL"),
                login_role=login_role,
                password=_environment_value(environment, "INGESTION_DATABASE_PASSWORD"),
            )
            print(f"Provisioned restricted database login {login_role}.")
        elif args.command == "audit-ingestion-runtime":
            login_role = environment.get(
                "INGESTION_DATABASE_LOGIN_ROLE", DEFAULT_INGESTION_LOGIN_ROLE
            )
            result = audit_ingestion_runtime(
                _environment_value(environment, "DATABASE_URL"),
                expected_login_role=login_role,
            )
            print(
                f"Database role audit passed for {result.current_user} "
                f"across {result.checked_relations} application relations."
            )
        elif args.command == "provision-oz-importer-runtime":
            login_role = environment.get(
                "OZ_IMPORTER_DATABASE_LOGIN_ROLE", DEFAULT_OZ_IMPORTER_LOGIN_ROLE
            )
            provision_oz_importer_runtime(
                _environment_value(environment, "MIGRATION_DATABASE_URL"),
                login_role=login_role,
                password=_environment_value(environment, "OZ_IMPORTER_DATABASE_PASSWORD"),
            )
            print(f"Provisioned restricted database login {login_role}.")
        elif args.command == "audit-oz-importer-runtime":
            login_role = environment.get(
                "OZ_IMPORTER_DATABASE_LOGIN_ROLE", DEFAULT_OZ_IMPORTER_LOGIN_ROLE
            )
            result = audit_oz_importer_runtime(
                _environment_value(environment, "DATABASE_URL"),
                expected_login_role=login_role,
            )
            print(
                f"Database role audit passed for {result.current_user} "
                f"across {result.checked_relations} application relations."
            )
        elif args.command == "provision-oz-membership-runtime":
            login_role = environment.get(
                "OZ_MEMBERSHIP_DATABASE_LOGIN_ROLE", DEFAULT_OZ_MEMBERSHIP_LOGIN_ROLE
            )
            provision_oz_membership_runtime(
                _environment_value(environment, "MIGRATION_DATABASE_URL"),
                login_role=login_role,
                password=_environment_value(environment, "OZ_MEMBERSHIP_DATABASE_PASSWORD"),
            )
            print(f"Provisioned restricted database login {login_role}.")
        else:
            login_role = environment.get(
                "OZ_MEMBERSHIP_DATABASE_LOGIN_ROLE", DEFAULT_OZ_MEMBERSHIP_LOGIN_ROLE
            )
            result = audit_oz_membership_runtime(
                _environment_value(environment, "DATABASE_URL"),
                expected_login_role=login_role,
            )
            print(
                f"Database role audit passed for {result.current_user} "
                f"across {result.checked_relations} application relations."
            )
    except (DatabaseRoleConfigurationError, DatabaseRoleAuditError) as error:
        build_parser().error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
