"""Candidate API contracts shared by live read-model projections."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
