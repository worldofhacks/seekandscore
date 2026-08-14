"""Evidence-backed operator research contracts."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from seekandscore.readmodels.candidates import CandidateReadModel


class ResearchStatus(StrEnum):
    WATCHING = "watching"
    RESEARCHING = "researching"
    PASSED = "passed"
    ARCHIVED = "archived"


class VerificationGateKey(StrEnum):
    PARCEL_IDENTITY = "parcel_identity"
    SOURCE_FRESHNESS = "source_freshness"
    OPPORTUNITY_ZONE = "opportunity_zone"
    UNDERWRITING = "underwriting"
    CONTACT_PREP = "contact_prep"


class VerificationGateStatus(StrEnum):
    SATISFIED = "satisfied"
    OPEN = "open"
    BLOCKED = "blocked"
    NOT_AVAILABLE = "not_available"


class VerificationGate(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: VerificationGateKey
    status: VerificationGateStatus
    reason_code: str
    detail: str
    evidence_ids: tuple[str, ...] = ()


class DossierControls(BaseModel):
    model_config = ConfigDict(frozen=True)

    contact_prep_enabled: bool = False
    outbound_enabled: bool = False


class ResearchCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    organization_id: UUID
    candidate_id: UUID
    region_id: str
    jurisdiction_id: str
    parcel_id: str
    status: ResearchStatus
    operator_note: str | None = Field(default=None, max_length=4000)
    next_action: str | None = Field(default=None, max_length=500)
    candidate_read_model_version: str
    candidate_as_of: datetime
    version: int = Field(ge=1)
    created_by: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime


class ResearchCasePage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[ResearchCase, ...]
    next_cursor: str | None
    total: int = Field(ge=0)


class CandidateDossier(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate: CandidateReadModel
    region_id: str
    gates: tuple[VerificationGate, ...]
    research_case: ResearchCase | None
    controls: DossierControls = DossierControls()
