"""Scheduler planning shell; it never performs ingestion itself."""

from dataclasses import dataclass

from seekandscore.platform.settings import AlertDeliveryMode, Settings


@dataclass(frozen=True, slots=True)
class DispatchReport:
    requested: int
    dispatched: int
    skipped: tuple[str, ...]


class SchedulerRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def dispatch_due(self) -> DispatchReport:
        """Describe safely skipped capabilities until a job ledger is connected."""

        skipped: list[str] = []
        if not self.settings.ingestion_enabled:
            skipped.append("ingestion_disabled")
        if self.settings.alert_delivery_mode is not AlertDeliveryMode.PROVIDER:
            skipped.append("external_alert_delivery_disabled")
        if not self.settings.outreach_send_enabled:
            skipped.append("outreach_send_disabled")
        return DispatchReport(requested=0, dispatched=0, skipped=tuple(skipped))

    def is_ready(self) -> bool:
        return True
