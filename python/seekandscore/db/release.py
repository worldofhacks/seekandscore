"""One-shot database release orchestration for the isolated Railway migration service."""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress

import sqlalchemy as sa
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy.pool import NullPool

from seekandscore.db.migrate import build_config
from seekandscore.db.roles import (
    DEFAULT_API_LOGIN_ROLE,
    DEFAULT_INGESTION_LOGIN_ROLE,
    DEFAULT_OZ_IMPORTER_LOGIN_ROLE,
    DEFAULT_OZ_MEMBERSHIP_LOGIN_ROLE,
    DatabaseRoleAuditError,
    DatabaseRoleConfigurationError,
    audit_api_runtime,
    audit_ingestion_runtime,
    audit_oz_importer_runtime,
    audit_oz_membership_runtime,
    provision_api_runtime,
    provision_ingestion_runtime,
    provision_oz_importer_runtime,
    provision_oz_membership_runtime,
)


class DatabaseReleaseError(RuntimeError):
    """Raised when an isolated schema/role release is incomplete."""


RELEASE_LOCK_NAMESPACE = 1_397_052_499


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "")
    if not value:
        raise DatabaseReleaseError(f"{name} is required by the database migration service")
    return value


@contextmanager
def database_release_lock(owner_database_url: str) -> Iterator[None]:
    """Hold a database-scoped session lock for the entire schema/role release.

    ``pg_try_advisory_lock`` is intentionally non-blocking: a duplicate Railway deployment fails
    closed instead of waiting an unbounded time or interleaving credential/grant reconciliation.
    """

    engine = sa.create_engine(
        owner_database_url,
        poolclass=NullPool,
        hide_parameters=True,
    )
    connection = engine.connect()
    lock_sql = sa.text("SELECT pg_try_advisory_lock(:namespace, hashtext(current_database()))")
    unlock_sql = sa.text("SELECT pg_advisory_unlock(:namespace, hashtext(current_database()))")
    acquired = False
    try:
        try:
            acquired = bool(connection.scalar(lock_sql, {"namespace": RELEASE_LOCK_NAMESPACE}))
        except sa.exc.SQLAlchemyError as error:
            raise DatabaseReleaseError("could not acquire the database release lock") from error
        if not acquired:
            raise DatabaseReleaseError(
                "another database schema/role release already holds the deployment lock"
            )
        yield
    finally:
        if acquired:
            with suppress(sa.exc.SQLAlchemyError):
                connection.execute(unlock_sql, {"namespace": RELEASE_LOCK_NAMESPACE})
                # Closing the session also releases every session-level advisory lock.
        connection.close()
        engine.dispose()


def _verify_schema_head(owner_database_url: str) -> str:
    config = build_config(owner_database_url)
    expected_head = ScriptDirectory.from_config(config).get_current_head()
    if expected_head is None:
        raise DatabaseReleaseError("Alembic has no current head")
    engine = sa.create_engine(
        owner_database_url,
        poolclass=NullPool,
        hide_parameters=True,
    )
    try:
        with engine.connect() as connection:
            actual_head = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
    except sa.exc.SQLAlchemyError as error:
        raise DatabaseReleaseError("could not verify the applied Alembic revision") from error
    finally:
        engine.dispose()
    if actual_head != expected_head:
        raise DatabaseReleaseError("database schema is not at the release Alembic head")
    return expected_head


def apply_release(environment: Mapping[str, str]) -> str:
    """Migrate with owner credentials, then reconcile and audit all runtime principals."""

    owner_url = _required(environment, "MIGRATION_DATABASE_URL")
    api_runtime_url = _required(environment, "API_RUNTIME_DATABASE_URL")
    ingestion_runtime_url = _required(environment, "INGESTION_RUNTIME_DATABASE_URL")
    oz_importer_runtime_url = _required(environment, "OZ_IMPORTER_RUNTIME_DATABASE_URL")
    oz_membership_runtime_url = _required(environment, "OZ_MEMBERSHIP_RUNTIME_DATABASE_URL")
    api_login = environment.get("API_DATABASE_LOGIN_ROLE", DEFAULT_API_LOGIN_ROLE)
    ingestion_login = environment.get("INGESTION_DATABASE_LOGIN_ROLE", DEFAULT_INGESTION_LOGIN_ROLE)
    oz_importer_login = environment.get(
        "OZ_IMPORTER_DATABASE_LOGIN_ROLE", DEFAULT_OZ_IMPORTER_LOGIN_ROLE
    )
    oz_membership_login = environment.get(
        "OZ_MEMBERSHIP_DATABASE_LOGIN_ROLE", DEFAULT_OZ_MEMBERSHIP_LOGIN_ROLE
    )

    with database_release_lock(owner_url):
        command.upgrade(build_config(owner_url), "head")
        provision_api_runtime(
            owner_url,
            login_role=api_login,
            password=_required(environment, "API_DATABASE_PASSWORD"),
        )
        provision_ingestion_runtime(
            owner_url,
            login_role=ingestion_login,
            password=_required(environment, "INGESTION_DATABASE_PASSWORD"),
        )
        provision_oz_importer_runtime(
            owner_url,
            login_role=oz_importer_login,
            password=_required(environment, "OZ_IMPORTER_DATABASE_PASSWORD"),
        )
        provision_oz_membership_runtime(
            owner_url,
            login_role=oz_membership_login,
            password=_required(environment, "OZ_MEMBERSHIP_DATABASE_PASSWORD"),
        )
        audit_api_runtime(api_runtime_url, expected_login_role=api_login)
        audit_ingestion_runtime(ingestion_runtime_url, expected_login_role=ingestion_login)
        audit_oz_importer_runtime(
            oz_importer_runtime_url,
            expected_login_role=oz_importer_login,
        )
        audit_oz_membership_runtime(
            oz_membership_runtime_url,
            expected_login_role=oz_membership_login,
        )
        return _verify_schema_head(owner_url)


def verify_release(environment: Mapping[str, str]) -> str:
    """Recheck schema and runtime identities without mutating grants or credentials."""

    owner_url = _required(environment, "MIGRATION_DATABASE_URL")
    api_login = environment.get("API_DATABASE_LOGIN_ROLE", DEFAULT_API_LOGIN_ROLE)
    ingestion_login = environment.get("INGESTION_DATABASE_LOGIN_ROLE", DEFAULT_INGESTION_LOGIN_ROLE)
    oz_importer_login = environment.get(
        "OZ_IMPORTER_DATABASE_LOGIN_ROLE", DEFAULT_OZ_IMPORTER_LOGIN_ROLE
    )
    oz_membership_login = environment.get(
        "OZ_MEMBERSHIP_DATABASE_LOGIN_ROLE", DEFAULT_OZ_MEMBERSHIP_LOGIN_ROLE
    )
    with database_release_lock(owner_url):
        audit_api_runtime(
            _required(environment, "API_RUNTIME_DATABASE_URL"),
            expected_login_role=api_login,
        )
        audit_ingestion_runtime(
            _required(environment, "INGESTION_RUNTIME_DATABASE_URL"),
            expected_login_role=ingestion_login,
        )
        audit_oz_importer_runtime(
            _required(environment, "OZ_IMPORTER_RUNTIME_DATABASE_URL"),
            expected_login_role=oz_importer_login,
        )
        audit_oz_membership_runtime(
            _required(environment, "OZ_MEMBERSHIP_RUNTIME_DATABASE_URL"),
            expected_login_role=oz_membership_login,
        )
        return _verify_schema_head(owner_url)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply or verify an isolated database release")
    parser.add_argument("command", choices=("apply", "verify"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        head = apply_release(os.environ) if args.command == "apply" else verify_release(os.environ)
    except (DatabaseReleaseError, DatabaseRoleAuditError, DatabaseRoleConfigurationError) as error:
        build_parser().error(str(error))
    print(f"Database release {args.command} passed at Alembic head {head}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
