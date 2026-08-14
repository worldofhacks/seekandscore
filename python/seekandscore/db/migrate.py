"""Alembic command wrapper used by local and Railway deployments."""

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from alembic import command
from alembic.config import Config

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEPLOYED_ENVIRONMENTS = frozenset({"staging", "production"})


class MigrationConfigurationError(ValueError):
    """Raised when a deployed migration could use runtime credentials."""


def resolve_database_url(
    explicit_url: str | None = None,
    *,
    environment: dict[str, str] | None = None,
) -> str | None:
    """Resolve a migration connection without silently using production runtime credentials.

    Local development and CI retain the historical ``DATABASE_URL`` fallback. Railway staging
    and production must provide the distinct owner credential as ``MIGRATION_DATABASE_URL``.
    """

    values = os.environ if environment is None else environment
    if explicit_url:
        return explicit_url
    migration_url = values.get("MIGRATION_DATABASE_URL")
    if migration_url:
        return migration_url
    app_env = values.get("APP_ENV", "development").strip().lower()
    if app_env in DEPLOYED_ENVIRONMENTS:
        raise MigrationConfigurationError(
            "MIGRATION_DATABASE_URL is required for staging/production migrations"
        )
    return values.get("DATABASE_URL")


def build_config(database_url: str | None = None) -> Config:
    config = Config(str(REPOSITORY_ROOT / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
        # migrations/env.py treats this explicit, already-resolved value as authoritative. The
        # attribute avoids DATABASE_URL overriding --database-url or MIGRATION_DATABASE_URL.
        config.attributes["seekandscore_database_url"] = database_url
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Seek and Score database migrations")
    parser.add_argument("command", choices=("upgrade", "downgrade", "current", "heads", "check"))
    parser.add_argument("revision", nargs="?")
    parser.add_argument("--database-url")
    parser.add_argument("--sql", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        database_url = resolve_database_url(args.database_url)
    except MigrationConfigurationError as error:
        build_parser().error(str(error))
    config = build_config(database_url)
    if args.command == "upgrade":
        command.upgrade(config, args.revision or "head", sql=args.sql)
    elif args.command == "downgrade":
        if not args.revision:
            build_parser().error("downgrade requires an explicit revision")
        command.downgrade(config, args.revision, sql=args.sql)
    elif args.command == "current":
        command.current(config, verbose=True)
    elif args.command == "heads":
        command.heads(config, verbose=True)
    else:
        command.check(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
