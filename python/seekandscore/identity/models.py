"""Identity-owned candidate contract."""

from enum import StrEnum
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field


class CandidateKind(StrEnum):
    PARCEL = "parcel"
    ASSEMBLAGE = "assemblage"


PARCEL_ID_NAMESPACE = UUID("97a9e56d-a6a3-444c-91e7-25558cc63f19")


def canonical_parcel_id(jurisdiction_id: str, local_parcel_id: str) -> UUID:
    """Return the stable identity shared by parcel, geography, and candidate projections."""

    return uuid5(PARCEL_ID_NAMESPACE, f"{jurisdiction_id}:{local_parcel_id}")


class CandidateIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    display_name: str = Field(min_length=1, max_length=160)
    kind: CandidateKind
    parcel_count: int = Field(ge=1)
    jurisdiction_id: str
