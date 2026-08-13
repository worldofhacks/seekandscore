"""Run a safe worker process."""

import argparse
import logging
from collections.abc import Sequence

from seekandscore.observability import configure_logging
from seekandscore.platform.settings import get_settings
from seekandscore.worker.runtime import WorkerRuntime, parse_queues

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Seek and Score worker")
    parser.add_argument("--queues", default="resolve,geo,market,score")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-cycles", type=int)
    parser.add_argument(
        "--run-source",
        help="run one source through the durable acquisition service, then exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    if args.run_source:
        from seekandscore.ingestion.__main__ import main as ingestion_main

        return ingestion_main(["run", "--source", args.run_source])
    try:
        queues = parse_queues(args.queues)
    except ValueError as error:
        build_parser().error(str(error))
    runtime = WorkerRuntime(settings, queues)
    logger.info(
        "worker starting",
        extra={
            "event": "worker.start",
            "service": "worker",
            "environment": settings.app_env,
            "release_sha": settings.release_sha,
        },
    )
    if args.once:
        report = runtime.run_cycle()
        logger.info(
            "worker cycle complete: runnable=%s blocked=%s jobs=%d",
            ",".join(report.runnable_queues),
            ",".join(report.blocked_queues),
            report.jobs_completed,
            extra={"event": "worker.once", "service": "worker"},
        )
        return 0
    return runtime.run_forever(args.poll_interval, args.max_cycles)


if __name__ == "__main__":
    raise SystemExit(main())
