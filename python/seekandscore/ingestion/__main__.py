"""Run one explicitly activated official-source acquisition."""

import argparse
import logging
from collections.abc import Sequence

from seekandscore.acquisition.models import SourceRunStatus
from seekandscore.ingestion.runner import build_acquisition_service
from seekandscore.observability import configure_logging
from seekandscore.platform.settings import get_settings

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Seek and Score source acquisition")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--source", default="travis_tcad_parcels")
    subparsers.add_parser("check")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    if args.command == "check":
        if not settings.ingestion_enabled:
            logger.info(
                "ingestion remains disabled",
                extra={"event": "ingestion.check", "service": "ingestion"},
            )
        return 0
    if args.source != settings.ingestion_source_id:
        build_parser().error("requested source does not match INGESTION_SOURCE_ID")
    service = build_acquisition_service(settings)
    try:
        run = service.execute(
            ingestion_enabled=settings.ingestion_enabled,
            dataset_mode=settings.dataset_mode,
            activation_id=settings.ingestion_activation_id,
        )
    finally:
        service.close()
    logger.info(
        "source run complete: status=%s records=%d observations=%d quarantined=%d",
        run.status,
        run.records_fetched,
        run.observations_created,
        run.records_quarantined,
        extra={"event": "ingestion.complete", "service": "ingestion"},
    )
    return 1 if run.status is SourceRunStatus.FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
