"""Identity-owned candidate contract."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CandidateKind(StrEnum):
    PARCEL = "parcel"
    ASSEMBLAGE = "assemblage"


class CandidateIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    display_name: str = Field(min_length=1, max_length=160)
    kind: CandidateKind
    parcel_count: int = Field(ge=1)
    jurisdiction_id: str
