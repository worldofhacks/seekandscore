"""Public, non-secret runtime capability projection."""

from pydantic import BaseModel, ConfigDict

from seekandscore.platform.settings import Settings


class PlatformCapabilities(BaseModel):
    """Safe subset of runtime feature state exposed to API clients."""

    model_config = ConfigDict(frozen=True)

    dataset_mode: str
    candidate_serving_mode: str
    candidate_read_model_ready: bool
    live_candidate_display_enabled: bool
    oz_2018_private_display_enabled: bool
    ingestion_enabled: bool
    research_writes_enabled: bool
    research_store_ready: bool
    alert_delivery_mode: str
    outreach_mode: str
    outreach_send_enabled: bool
    outreach_human_approval_required: bool
    external_effects_enabled: bool

    @classmethod
    def from_runtime(
        cls,
        settings: Settings,
        *,
        candidate_serving_mode: str,
        candidate_read_model_ready: bool,
        live_candidate_display_enabled: bool,
        research_store_ready: bool,
    ) -> "PlatformCapabilities":
        return cls(
            dataset_mode=settings.dataset_mode,
            candidate_serving_mode=candidate_serving_mode,
            candidate_read_model_ready=candidate_read_model_ready,
            live_candidate_display_enabled=live_candidate_display_enabled,
            oz_2018_private_display_enabled=settings.oz_2018_private_display_enabled,
            ingestion_enabled=settings.ingestion_enabled,
            research_writes_enabled=settings.research_writes_enabled,
            research_store_ready=research_store_ready,
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
