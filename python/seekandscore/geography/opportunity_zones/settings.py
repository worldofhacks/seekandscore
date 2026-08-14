"""Dedicated fail-closed settings for the federal geography importer."""

from enum import StrEnum

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from seekandscore.geography.opportunity_zones.membership import (
    OZ_MEMBERSHIP_BUILD_ACTIVATION_ID,
)
from seekandscore.geography.opportunity_zones.source import CDFI_QOZ_2018_ACTIVATION_ID


class ImportEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PREVIEW = "preview"
    STAGING = "staging"
    PRODUCTION = "production"


class OpportunityZoneImportSettings(BaseSettings):
    """The source is inert unless every independent import gate is satisfied."""

    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: ImportEnvironment = ImportEnvironment.DEVELOPMENT
    oz_2018_import_enabled: bool = False
    oz_2018_import_activation_id: str | None = None
    oz_2018_membership_build_enabled: bool = False
    oz_2018_membership_build_activation_id: str | None = None
    database_url: str | None = None
    object_storage_endpoint: str | None = None
    object_storage_region: str = "auto"
    object_storage_bucket: str | None = None
    object_storage_access_key_id: str | None = Field(default=None, repr=False)
    object_storage_secret_access_key: str | None = Field(default=None, repr=False)
    object_storage_prefix: str = "raw-artifacts"
    object_storage_force_path_style: bool = False
    oz_2018_http_timeout_seconds: float = Field(default=120.0, gt=0, le=300)
    oz_2018_max_retries: int = Field(default=3, ge=0, le=5)

    @model_validator(mode="after")
    def validate_import_activation(self) -> "OpportunityZoneImportSettings":
        enabled = self.oz_2018_import_enabled or self.oz_2018_membership_build_enabled
        if enabled and self.app_env not in {
            ImportEnvironment.STAGING,
            ImportEnvironment.PRODUCTION,
        }:
            raise ValueError("2018 QOZ mutation can run only in staging or production")
        if enabled and not self.database_url:
            raise ValueError("2018 QOZ mutation requires DATABASE_URL")
        if self.oz_2018_import_enabled:
            if self.oz_2018_import_activation_id != CDFI_QOZ_2018_ACTIVATION_ID:
                raise ValueError("2018 QOZ import requires the exact reviewed activation ID")
            if not all(
                (
                    self.object_storage_endpoint,
                    self.object_storage_bucket,
                    self.object_storage_access_key_id,
                    self.object_storage_secret_access_key,
                )
            ):
                raise ValueError("2018 QOZ import requires durable S3-compatible artifact storage")
        if self.oz_2018_membership_build_enabled and (
            self.oz_2018_membership_build_activation_id != OZ_MEMBERSHIP_BUILD_ACTIVATION_ID
        ):
            raise ValueError("2018 QOZ membership build requires the exact reviewed activation ID")
        return self
