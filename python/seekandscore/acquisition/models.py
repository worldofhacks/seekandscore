"""Immutable acquisition, provenance, and observation contracts."""

import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AuthorityLevel(StrEnum):
    OFFICIAL_DERIVATIVE = "official_derivative"


class SourceRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    SUCCEEDED_UNCHANGED = "succeeded_unchanged"
    PARTIAL = "partial"
    FAILED = "failed"


class SourceRunProfile(StrEnum):
    PROOF = "proof"
    COHORT = "cohort"


class AcquisitionCompletenessPolicy(StrEnum):
    ALLOW_BOUNDED_PARTIAL = "allow_bounded_partial"
    REQUIRE_COMPLETE = "require_complete"


class FreshnessStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"
    NEVER = "never"


class SourceDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    authority: str
    authority_level: AuthorityLevel
    jurisdiction_id: str
    capability: str
    original_uri: str
    query_uri: str
    terms_uri: str
    attribution_text: str
    use_limitation: str
    cadence: str
    freshness_days: int = Field(gt=0)
    geographic_vintage: str
    adapter_version: str
    parser_version: str
    contains_personal_data: bool = False
    display_allowed: bool = False
    export_allowed: bool = False
    redistribution_allowed: bool = False


class RawArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    source_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_count: int = Field(ge=0)
    media_type: str
    storage_uri: str
    original_uri: str
    request_params: dict[str, str | int | bool]
    response_etag: str | None = None
    retrieved_at: datetime
    published_at: datetime | None = None
    effective_at: datetime | None = None


class SourceRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    source_id: str
    status: SourceRunStatus
    requested_at: datetime
    started_at: datetime
    completed_at: datetime | None = None
    retrieved_at: datetime | None = None
    records_fetched: int = Field(default=0, ge=0)
    observations_created: int = Field(default=0, ge=0)
    records_quarantined: int = Field(default=0, ge=0)
    artifact_ids: tuple[UUID, ...] = ()
    unchanged_artifact_id: UUID | None = None
    partial: bool = False
    error_code: str | None = None
    error_detail: str | None = None
    adapter_version: str
    parser_version: str
    run_profile: SourceRunProfile = SourceRunProfile.PROOF
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_id: str

    @property
    def is_complete_cohort(self) -> bool:
        return bool(
            self.run_profile is SourceRunProfile.COHORT
            and self.status in {SourceRunStatus.SUCCEEDED, SourceRunStatus.SUCCEEDED_UNCHANGED}
            and not self.partial
            and self.records_quarantined == 0
            and self.artifact_ids
        )


class NormalizedParcelObservation(BaseModel):
    """A source assertion, not a resolved parcel fact or valuation."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    source_id: str
    source_record_id: str
    artifact_id: UUID
    artifact_sha256: str
    parser_version: str
    jurisdiction_id: str
    local_parcel_id: str
    geographic_id: str | None
    situs_address: str | None
    situs_city: str | None
    situs_zip: str | None
    tcad_acres: float | None = Field(default=None, gt=0)
    gis_acres: float | None = Field(default=None, gt=0)
    market_value_cents: int | None = Field(default=None, ge=0)
    appraised_value_cents: int | None = Field(default=None, ge=0)
    assessed_value_cents: int | None = Field(default=None, ge=0)
    improvement_value_cents: int | None = Field(default=None, ge=0)
    land_value_cents: int | None = Field(default=None, ge=0)
    first_improvement_year: int | None = Field(default=None, ge=1700, le=2100)
    geometry_srid: Literal[4326] | None = None
    geometry_geojson: str | None = None
    observed_at: datetime
    screening_only: bool = True

    @model_validator(mode="after")
    def require_complete_geometry_pair(self) -> "NormalizedParcelObservation":
        if (self.geometry_srid is None) != (self.geometry_geojson is None):
            raise ValueError("parcel geometry SRID and GeoJSON must be provided together")
        return self

    @field_validator("geometry_geojson")
    @classmethod
    def require_multipolygon_geojson(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            geometry: Any = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("parcel geometry must be valid GeoJSON") from error
        if not isinstance(geometry, dict) or geometry.get("type") != "MultiPolygon":
            raise ValueError("parcel geometry must be a GeoJSON MultiPolygon")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise ValueError("parcel geometry must contain polygon coordinates")
        return value


class QuarantinedRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    source_id: str
    artifact_id: UUID
    source_record_id: str | None
    reason_code: str
    reason_detail: str
    recorded_at: datetime
