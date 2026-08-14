"""Run or inspect the separately activated 2018 QOZ importer."""

import argparse
import logging
from collections.abc import Sequence

from seekandscore.geography.opportunity_zones.membership import (
    OpportunityZoneMembershipBuildDisabledError,
    OpportunityZoneMembershipError,
)
from seekandscore.geography.opportunity_zones.models import OpportunityZoneImportStatus
from seekandscore.geography.opportunity_zones.runtime import (
    build_import_service,
    build_membership_service,
)
from seekandscore.geography.opportunity_zones.settings import OpportunityZoneImportSettings
from seekandscore.observability import configure_logging

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import frozen official 2018 QOZ geography")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run")
    commands.add_parser("build")
    commands.add_parser("verify")
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
        logger.info(
            "2018 QOZ membership builder enabled=%s",
            settings.oz_2018_membership_build_enabled,
            extra={"event": "geography.qoz2018.membership.check", "service": "federal-geography"},
        )
        return 0
    if args.command in {"build", "verify"}:
        if args.command == "build" and not settings.oz_2018_membership_build_enabled:
            logger.error("2018 QOZ membership builder remains disabled")
            return 2
        membership_service = build_membership_service(settings)
        try:
            outcome = (
                membership_service.build(
                    build_enabled=settings.oz_2018_membership_build_enabled,
                    activation_id=settings.oz_2018_membership_build_activation_id,
                )
                if args.command == "build"
                else membership_service.verify()
            )
        except (
            OpportunityZoneMembershipBuildDisabledError,
            OpportunityZoneMembershipError,
        ) as error:
            logger.error("2018 QOZ membership %s failed: %s", args.command, error)
            return 1
        finally:
            membership_service.close()
        logger.info(
            "2018 QOZ membership %s: status=%s inside=%d outside=%d boundary_review=%d",
            args.command,
            outcome.status,
            outcome.inside_count,
            outcome.outside_count,
            outcome.boundary_review_count,
            extra={
                "event": f"geography.qoz2018.membership.{args.command}",
                "service": "federal-geography",
            },
        )
        return 0
    if not settings.oz_2018_import_enabled:
        logger.error("2018 QOZ importer remains disabled")
        return 2
    import_service = build_import_service(settings)
    try:
        run = import_service.execute(
            import_enabled=settings.oz_2018_import_enabled,
            activation_id=settings.oz_2018_import_activation_id,
        )
    finally:
        import_service.close()
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
