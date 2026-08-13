"""Typed, fail-closed runtime settings."""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PREVIEW = "preview"
    STAGING = "staging"
    PRODUCTION = "production"


class DatasetMode(StrEnum):
    SYNTHETIC = "synthetic"
    LIVE = "live"


class AlertDeliveryMode(StrEnum):
    DISABLED = "disabled"
    LOG = "log"
    PROVIDER = "provider"


class OutreachMode(StrEnum):
    DISABLED = "disabled"
    MANUAL = "manual"
    PROVIDER = "provider"


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables.

    External acquisition, alert, and outreach effects all require explicit activation.
    Defaults are safe for a fresh checkout and a Railway preview deployment.
    """

    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "seekandscore-api"
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    release_sha: str = "development"

    dataset_mode: DatasetMode = DatasetMode.SYNTHETIC
    ingestion_enabled: bool = False
    ingestion_activation_id: str | None = None

    alert_delivery_mode: AlertDeliveryMode = AlertDeliveryMode.LOG
    alert_delivery_provider: str | None = None
    alert_delivery_activation_id: str | None = None

    outreach_mode: OutreachMode = OutreachMode.DISABLED
    outreach_send_enabled: bool = False
    outreach_human_approval_required: bool = True
    outreach_policy_id: str = "acquisition-outreach-safe-default-v1"
    outreach_activation_id: str | None = None
    outreach_legal_review_id: str | None = None
    outreach_provider: str | None = None

    database_url: str | None = None
    redis_url: str | None = None

    @model_validator(mode="after")
    def validate_effect_activation(self) -> "Settings":
        """Reject ambiguous or unsafe external-effect configurations."""

        if self.ingestion_enabled:
            if self.app_env in {
                AppEnvironment.DEVELOPMENT,
                AppEnvironment.TEST,
                AppEnvironment.PREVIEW,
            }:
                raise ValueError("ingestion cannot be enabled in development, test, or preview")
            if self.dataset_mode is not DatasetMode.LIVE:
                raise ValueError("enabled ingestion requires DATASET_MODE=live")
            if not self.ingestion_activation_id:
                raise ValueError("enabled ingestion requires INGESTION_ACTIVATION_ID")

        if self.alert_delivery_mode is AlertDeliveryMode.PROVIDER:
            if self.app_env is not AppEnvironment.PRODUCTION:
                raise ValueError("provider alert delivery is production-only")
            if not self.alert_delivery_provider or not self.alert_delivery_activation_id:
                raise ValueError(
                    "provider alert delivery requires a provider and activation record"
                )

        if self.outreach_send_enabled:
            if self.app_env is not AppEnvironment.PRODUCTION:
                raise ValueError("outreach provider sends are production-only")
            if self.outreach_mode is not OutreachMode.PROVIDER:
                raise ValueError("enabled outreach sends require OUTREACH_MODE=provider")
            if not self.outreach_human_approval_required:
                raise ValueError("outreach sends require human approval")
            if not all(
                (
                    self.outreach_activation_id,
                    self.outreach_legal_review_id,
                    self.outreach_provider,
                    self.outreach_policy_id,
                )
            ):
                raise ValueError(
                    "outreach sends require provider, policy, legal-review, and activation records"
                )

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one validated settings object per process."""

    return Settings()
