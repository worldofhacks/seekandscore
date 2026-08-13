"""Run scheduler one-shot commands."""

import argparse
import logging
from collections.abc import Sequence

from seekandscore.observability import configure_logging
from seekandscore.platform.settings import get_settings
from seekandscore.scheduler.runtime import SchedulerRuntime

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Seek and Score scheduler")
    parser.add_argument("command", choices=("dispatch-due", "check"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    runtime = SchedulerRuntime(settings)
    if args.command == "check":
        return 0 if runtime.is_ready() else 1
    report = runtime.dispatch_due()
    logger.info(
        "scheduler dispatch complete: requested=%d dispatched=%d skipped=%s",
        report.requested,
        report.dispatched,
        ",".join(report.skipped),
        extra={
            "event": "scheduler.dispatch",
            "service": "scheduler",
            "environment": settings.app_env,
            "release_sha": settings.release_sha,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
