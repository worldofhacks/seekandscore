"""Public, non-secret runtime capability projection."""

from pydantic import BaseModel, ConfigDict

from seekandscore.platform.settings import Settings


class PlatformCapabilities(BaseModel):
    """Safe subset of runtime feature state exposed to API clients."""

    model_config = ConfigDict(frozen=True)

    dataset_mode: str
    ingestion_enabled: bool
    alert_delivery_mode: str
    outreach_mode: str
    outreach_send_enabled: bool
    outreach_human_approval_required: bool
    external_effects_enabled: bool

    @classmethod
    def from_settings(cls, settings: Settings) -> "PlatformCapabilities":
        return cls(
            dataset_mode=settings.dataset_mode,
            ingestion_enabled=settings.ingestion_enabled,
            alert_delivery_mode=settings.alert_delivery_mode,
            outreach_mode=settings.outreach_mode,
            outreach_send_enabled=settings.outreach_send_enabled,
            outreach_human_approval_required=settings.outreach_human_approval_required,
            external_effects_enabled=(
                settings.ingestion_enabled
                or settings.outreach_send_enabled
                or settings.alert_delivery_mode == "provider"
            ),
        )
