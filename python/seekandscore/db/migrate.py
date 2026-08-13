"""Alembic command wrapper used by local and Railway deployments."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from alembic import command
from alembic.config import Config

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def build_config(database_url: str | None = None) -> Config:
    config = Config(str(REPOSITORY_ROOT / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
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
    config = build_config(args.database_url)
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
