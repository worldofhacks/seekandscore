"""Run or inspect the separately activated 2018 QOZ importer."""

import argparse
import logging
from collections.abc import Sequence

from seekandscore.geography.opportunity_zones.models import OpportunityZoneImportStatus
from seekandscore.geography.opportunity_zones.runtime import build_import_service
from seekandscore.geography.opportunity_zones.settings import OpportunityZoneImportSettings
from seekandscore.observability import configure_logging

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import frozen official 2018 QOZ geography")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run")
    commands.add_parser("check")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = OpportunityZoneImportSettings()
    configure_logging("INFO")
    if args.command == "check":
        logger.info(
            "2018 QOZ importer enabled=%s",
            settings.oz_2018_import_enabled,
            extra={"event": "geography.qoz2018.check", "service": "federal-geography"},
        )
        return 0
    if not settings.oz_2018_import_enabled:
        logger.error("2018 QOZ importer remains disabled")
        return 2
    service = build_import_service(settings)
    try:
        run = service.execute(
            import_enabled=settings.oz_2018_import_enabled,
            activation_id=settings.oz_2018_import_activation_id,
        )
    finally:
        service.close()
    logger.info(
        "2018 QOZ import complete: status=%s tracts=%d",
        run.status,
        run.imported_tracts,
        extra={"event": "geography.qoz2018.complete", "service": "federal-geography"},
    )
    return (
        0
        if run.status
        in {
            OpportunityZoneImportStatus.SUCCEEDED,
            OpportunityZoneImportStatus.SUCCEEDED_UNCHANGED,
        }
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
