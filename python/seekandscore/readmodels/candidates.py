"""Deterministic, explicitly synthetic candidate projection."""

import base64
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from seekandscore.identity import CandidateIdentity, CandidateKind
from seekandscore.registry import InMemoryGeographyRegistry
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
    status: str
    retrieved_at: datetime | None = None
    published_at: datetime | None = None
    record_count: int | None = Field(default=None, ge=0)
    detail: str | None = None


class CandidateReadModel(BaseModel):
    """API projection; synthetic fixtures contain no owner or contact data."""

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
    synthetic: bool = True
    read_model_version: str = READ_MODEL_VERSION
    screening_only: bool = False
    source_observation: SourceObservation | None = None


class CandidatePage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[CandidateReadModel, ...]
    next_cursor: str | None
    total: int = Field(ge=0)
    dataset_mode: str
    dataset_status: str = "synthetic"
    retrieved_at: datetime | None = None
    published_at: datetime | None = None
    stale_after: datetime | None = None
    partial: bool = False
    sources: tuple[CandidateSourceSummary, ...] = ()
    warnings: tuple[str, ...] = ()
    read_model_version: str = READ_MODEL_VERSION


class InvalidCursorError(ValueError):
    """Raised when a cursor is not one issued by this projection."""


class SyntheticCandidateRepository:
    """Stable fixture-backed projection used before approved source ingestion."""

    def __init__(self, geography: InMemoryGeographyRegistry) -> None:
        self._items = _build_items(geography)
        self._by_id = {item.id: item for item in self._items}
        if len(self._items) != len(self._by_id):
            raise ValueError("synthetic candidate identifiers must be unique")

    def list(self, *, limit: int, cursor: str | None, dataset_mode: str) -> CandidatePage:
        offset = _decode_cursor(cursor) if cursor else 0
        if offset > len(self._items):
            raise InvalidCursorError("cursor is beyond the current result set")
        end = min(offset + limit, len(self._items))
        next_cursor = _encode_cursor(end) if end < len(self._items) else None
        return CandidatePage(
            items=self._items[offset:end],
            next_cursor=next_cursor,
            total=len(self._items),
            dataset_mode=dataset_mode,
            dataset_status="synthetic" if dataset_mode == "synthetic" else "fallback",
            warnings=(
                ()
                if dataset_mode == "synthetic"
                else ("Live mode has no candidate projection; serving labeled synthetic data.",)
            ),
        )

    def get(self, candidate_id: UUID) -> CandidateReadModel | None:
        return self._by_id.get(candidate_id)

    def is_ready(self) -> bool:
        return bool(self._items) and all(item.synthetic for item in self._items)


def _encode_cursor(offset: int) -> str:
    value = f"{READ_MODEL_VERSION}:{offset}".encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode_cursor(cursor: str) -> int:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=True).decode()
        version, offset_text = raw.rsplit(":", maxsplit=1)
        offset = int(offset_text)
    except (ValueError, UnicodeDecodeError) as error:
        raise InvalidCursorError("cursor is malformed") from error
    if version != READ_MODEL_VERSION or offset < 0:
        raise InvalidCursorError("cursor does not match this read-model version")
    return offset


def _build_items(geography: InMemoryGeographyRegistry) -> tuple[CandidateReadModel, ...]:
    fixture_time = datetime(2026, 8, 12, 12, tzinfo=UTC)
    fixtures = (
        (
            CandidateIdentity(
                id=UUID("11111111-1111-4111-8111-111111111111"),
                display_name="Synthetic East Austin infill parcel",
                kind=CandidateKind.PARCEL,
                parcel_count=1,
                jurisdiction_id="us-tx-travis",
            ),
            "infill",
            1,
            3,
            CandidateQueueState.READY,
            87.4,
            0.82,
            2.4,
            MoneyRange(low=980_000, high=1_260_000),
            795_000,
            "Airport-corridor access and a conservative land basis justify focused verification.",
            OpportunityZoneStatus.EFFECTIVE,
            "Verify access and utility capacity",
            "Access evidence was refreshed in the synthetic snapshot.",
            EvidenceSummary(source_count=5, unresolved_conflict_count=0, freshness="current"),
            "East Austin, TX",
            "TX-453-SYN-API-001",
        ),
        (
            CandidateIdentity(
                id=UUID("22222222-2222-4222-8222-222222222222"),
                display_name="Synthetic Bastrop growth parcel",
                kind=CandidateKind.PARCEL,
                parcel_count=1,
                jurisdiction_id="us-tx-bastrop",
            ),
            "land-banking",
            2,
            1,
            CandidateQueueState.RESEARCH,
            82.1,
            0.76,
            18.7,
            MoneyRange(low=690_000, high=880_000),
            565_000,
            "Growth-corridor optionality is promising, with entitlement evidence still unresolved.",
            OpportunityZoneStatus.OUTSIDE,
            "Review entitlement and frontage evidence",
            None,
            EvidenceSummary(source_count=4, unresolved_conflict_count=1, freshness="current"),
            "Bastrop, TX",
            "TX-021-SYN-API-002",
        ),
        (
            CandidateIdentity(
                id=UUID("33333333-3333-4333-8333-333333333333"),
                display_name="Synthetic Caldwell County assemblage",
                kind=CandidateKind.ASSEMBLAGE,
                parcel_count=3,
                jurisdiction_id="us-tx-caldwell",
            ),
            "assemblage",
            3,
            None,
            CandidateQueueState.NEW,
            78.8,
            0.68,
            42.3,
            MoneyRange(low=850_000, high=1_110_000),
            735_000,
            "A multi-parcel land-bank candidate remains research-only until lineage is resolved.",
            OpportunityZoneStatus.REVIEW,
            "Resolve boundary overlap and parcel lineage",
            "New after three synthetic parcel identities were associated.",
            EvidenceSummary(source_count=3, unresolved_conflict_count=2, freshness="review"),
            "Lockhart, TX",
            "TX-055-SYN-API-003",
        ),
    )

    items: list[CandidateReadModel] = []
    for (
        identity,
        strategy,
        rank,
        previous_rank,
        queue_state,
        score,
        confidence,
        acreage,
        value_range,
        likely_basis,
        thesis,
        oz_status,
        next_action,
        material_change,
        evidence,
        locality,
        parcel_id,
    ) in fixtures:
        jurisdiction = geography.get(identity.jurisdiction_id)
        if jurisdiction is None:
            raise ValueError(f"missing jurisdiction {identity.jurisdiction_id}")
        items.append(
            CandidateReadModel(
                id=identity.id,
                display_name=identity.display_name,
                locality=locality,
                parcel_id=parcel_id,
                candidate_kind=identity.kind,
                parcel_count=identity.parcel_count,
                jurisdiction_id=jurisdiction.id,
                county_name=jurisdiction.county_name,
                state_name=jurisdiction.state_name,
                timezone=jurisdiction.timezone,
                strategy=strategy,
                rank=rank,
                previous_rank=previous_rank,
                queue_state=queue_state,
                opportunity_score=score,
                confidence=confidence,
                acreage=acreage,
                value_range=value_range,
                likely_basis=likely_basis,
                thesis=thesis,
                opportunity_zone_status=oz_status,
                next_action=next_action,
                material_change=material_change,
                evidence=evidence,
                as_of=fixture_time,
            )
        )
    return tuple(items)
