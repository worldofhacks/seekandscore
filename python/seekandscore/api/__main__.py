"""Run the API with Uvicorn."""

import argparse
from collections.abc import Sequence

import uvicorn

from seekandscore.bootstrap import AppContainer
from seekandscore.platform.settings import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Seek and Score API")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate configuration and module readiness, then exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    container = AppContainer.build(settings)
    if args.check:
        return 0 if all(container.readiness_checks().values()) else 1
    uvicorn.run(
        "seekandscore.api:app",
        host=args.host or settings.host,
        port=args.port or settings.port,
        log_level=settings.log_level.lower(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
