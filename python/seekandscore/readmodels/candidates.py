"""Candidate API contracts shared by live read-model projections."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from seekandscore.geography.opportunity_zones.models import (
    OpportunityZoneClassification,
    OpportunityZoneEvidence,
    OpportunityZoneEvidenceReason,
)
from seekandscore.identity import CandidateKind
from seekandscore.version import READ_MODEL_VERSION


class OpportunityZoneStatus(StrEnum):
    EFFECTIVE = "effective"
    OUTSIDE = "outside"
    REVIEW = "review"


class CandidateQueueState(StrEnum):
    NEW = "new"
    RESEARCH = "research"
    WATCHING = "watching"
    READY = "ready"


class CandidateCity(StrEnum):
    """Cities approved for the bounded Travis assessor cohort."""

    DEL_VALLE = "DEL VALLE"
    MANOR = "MANOR"


class CandidateAppliedFilters(BaseModel):
    """Canonical filters echoed by the candidate explorer response."""

    model_config = ConfigDict(frozen=True)

    q: str | None = Field(default=None, max_length=100)
    city: CandidateCity | None = None
    min_acres: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_acres: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("q")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_acreage_range(self) -> "CandidateAppliedFilters":
        if (
            self.min_acres is not None
            and self.max_acres is not None
            and self.min_acres > self.max_acres
        ):
            raise ValueError("min_acres must be less than or equal to max_acres")
        return self


class MoneyRange(BaseModel):
    model_config = ConfigDict(frozen=True)

    low: int = Field(ge=0)
    high: int = Field(ge=0)


class EvidenceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_count: int = Field(ge=0)
    unresolved_conflict_count: int = Field(ge=0)
    freshness: str


class SourceObservationFields(BaseModel):
    model_config = ConfigDict(frozen=True)

    market_value_cents: int | None = Field(default=None, ge=0)
    appraised_value_cents: int | None = Field(default=None, ge=0)
    assessed_value_cents: int | None = Field(default=None, ge=0)
    land_value_cents: int | None = Field(default=None, ge=0)
    improvement_value_cents: int | None = Field(default=None, ge=0)
    acreage: float | None = Field(default=None, gt=0)


class SourceObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    source_record_id: str
    artifact_sha256: str
    retrieved_at: datetime
    fields: SourceObservationFields


class CandidateSourceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    status: Literal["current", "stale", "error", "unavailable", "unknown"]
    retrieved_at: datetime | None = None
    published_at: datetime | None = None
    record_count: int | None = Field(default=None, ge=0)
    detail: str | None = None


class CandidateReadModel(BaseModel):
    """Live API projection; owner and contact data are intentionally excluded."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    display_name: str
    locality: str
    parcel_id: str
    candidate_kind: CandidateKind
    parcel_count: int
    jurisdiction_id: str
    county_name: str
    state_name: str
    timezone: str
    strategy: str
    rank: int = Field(ge=1)
    previous_rank: int | None = Field(default=None, ge=1)
    queue_state: CandidateQueueState
    opportunity_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    acreage: float = Field(gt=0)
    value_range: MoneyRange
    likely_basis: int = Field(ge=0)
    thesis: str
    opportunity_zone_status: OpportunityZoneStatus
    opportunity_zone_evidence: OpportunityZoneEvidence = OpportunityZoneEvidence(
        classification=OpportunityZoneClassification.UNAVAILABLE,
        reason_code=OpportunityZoneEvidenceReason.MEMBERSHIP_SNAPSHOT_UNAVAILABLE,
    )
    next_action: str
    material_change: str | None = None
    evidence: EvidenceSummary
    as_of: datetime
    read_model_version: str = READ_MODEL_VERSION
    screening_only: bool = False
    source_observation: SourceObservation | None = None


class CandidatePage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[CandidateReadModel, ...]
    next_cursor: str | None
    total: int = Field(ge=0)
    cohort_total: int = Field(default=0, ge=0)
    applied_filters: CandidateAppliedFilters = CandidateAppliedFilters()
    dataset_mode: Literal["live"]
    dataset_status: Literal["current", "stale", "partial", "error"] = "error"
    retrieved_at: datetime | None = None
    published_at: datetime | None = None
    stale_after: datetime | None = None
    partial: bool = False
    sources: tuple[CandidateSourceSummary, ...] = ()
    warnings: tuple[str, ...] = ()
    read_model_version: str = READ_MODEL_VERSION


class InvalidCursorError(ValueError):
    """Raised when a cursor is not one issued by this projection."""
