"""Domain records for source-pinned Opportunity Zone geography."""

import json
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DesignationStatus(StrEnum):
    """Publication stage; eligibility and nomination are not designations."""

    ELIGIBLE = "eligible"
    STATE_NOMINATED = "state_nominated"
    TREASURY_CERTIFIED = "treasury_certified"
    EFFECTIVE = "effective"
    EXPIRED = "expired"


class TemporalPrecision(StrEnum):
    EXACT = "exact"
    YEAR = "year"


class OpportunityZoneRound(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    round_code: str
    census_vintage: int
    certification_status: DesignationStatus
    designation_status: DesignationStatus
    effective_from: date
    effective_to: date
    tract_intervals_vary: bool = False
    source_id: str
    source_artifact_id: UUID
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_uri: str

    @model_validator(mode="after")
    def reject_unreviewed_2027_effective_status(self) -> "OpportunityZoneRound":
        if self.round_code == "2027" and self.designation_status is DesignationStatus.EFFECTIVE:
            raise ValueError(
                "2027 eligibility or nomination data cannot be represented as effective"
            )
        if self.effective_from > self.effective_to:
            raise ValueError("effective interval ends before it begins")
        return self


class OpportunityZoneTract(BaseModel):
    """One tract geometry asserted by one immutable official artifact."""

    model_config = ConfigDict(frozen=True)

    round_id: str
    tract_geoid: str = Field(pattern=r"^[0-9]{11}$")
    census_vintage: int
    certification_status: DesignationStatus
    designation_status: DesignationStatus
    effective_from: date
    effective_from_precision: TemporalPrecision
    effective_to: date
    state_name: str = Field(min_length=1, max_length=80)
    county_name: str = Field(min_length=1, max_length=120)
    source_artifact_id: UUID
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    geometry_srid: int
    geometry_geojson: str

    @model_validator(mode="after")
    def require_valid_effective_interval(self) -> "OpportunityZoneTract":
        if self.effective_from > self.effective_to:
            raise ValueError("effective interval ends before it begins")
        return self

    @field_validator("geometry_geojson")
    @classmethod
    def require_multipolygon_geojson(cls, value: str) -> str:
        try:
            geometry: Any = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("geometry must be valid GeoJSON") from error
        if not isinstance(geometry, dict) or geometry.get("type") != "MultiPolygon":
            raise ValueError("geometry must be a GeoJSON MultiPolygon")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise ValueError("geometry must contain polygon coordinates")
        return value


class OpportunityZoneImportStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    SUCCEEDED_UNCHANGED = "succeeded_unchanged"
    FAILED = "failed"


class OpportunityZoneImportRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    source_id: str
    status: OpportunityZoneImportStatus
    activation_id: str
    started_at: datetime
    completed_at: datetime | None = None
    source_artifact_id: UUID | None = None
    source_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    expected_tracts: int = Field(gt=0)
    imported_tracts: int = Field(default=0, ge=0)
    error_code: str | None = None
    error_detail: str | None = None


class ImportOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    inserted_tracts: int = Field(ge=0)
    total_tracts: int = Field(ge=0)
    unchanged: bool = False
