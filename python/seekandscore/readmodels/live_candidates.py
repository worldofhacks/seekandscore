"""Internal assessor-screen projection built from latest source observations."""

import base64
from datetime import datetime
from uuid import UUID, uuid5

import sqlalchemy as sa

from seekandscore.acquisition.models import (
    FreshnessStatus,
    NormalizedParcelObservation,
    SourceRunStatus,
)
from seekandscore.acquisition.repository import AcquisitionRepository
from seekandscore.identity import CandidateKind
from seekandscore.readmodels.candidates import (
    CandidatePage,
    CandidateQueueState,
    CandidateReadModel,
    CandidateSourceSummary,
    EvidenceSummary,
    InvalidCursorError,
    MoneyRange,
    OpportunityZoneStatus,
    SourceObservation,
    SourceObservationFields,
)
from seekandscore.registry import InMemorySourceRegistry
from seekandscore.version import READ_MODEL_VERSION

LIVE_CANDIDATE_NAMESPACE = UUID("97a9e56d-a6a3-444c-91e7-25558cc63f19")
LIVE_SOURCE_ID = "travis_tcad_parcels"


class CandidateReadUnavailableError(RuntimeError):
    """The live candidate projection cannot currently serve a request."""


class UnavailableCandidateRepository:
    """Fail-closed projection used when no live observation store is configured."""

    serving_mode = "unavailable"
    display_enabled = False

    def __init__(self, sources: InMemorySourceRegistry, *, reason: str) -> None:
        self.sources = sources
        self.reason = reason

    def list(self, *, limit: int, cursor: str | None, dataset_mode: str) -> CandidatePage:
        del limit, cursor
        return _empty_page(
            sources=self.sources,
            dataset_mode=dataset_mode,
            source_status="unavailable",
            warning=self.reason,
        )

    def get(self, candidate_id: UUID) -> CandidateReadModel | None:
        del candidate_id
        raise CandidateReadUnavailableError(self.reason)

    def is_ready(self) -> bool:
        return False


class LiveCandidateRepository:
    """Reads durable observations; it does not perform acquisition or inference."""

    serving_mode = "live"

    def __init__(
        self,
        acquisition: AcquisitionRepository,
        sources: InMemorySourceRegistry,
        *,
        display_enabled: bool,
    ) -> None:
        self.acquisition = acquisition
        self.sources = sources
        source = sources.get(LIVE_SOURCE_ID)
        self.display_enabled = bool(
            display_enabled and source is not None and source.display_allowed
        )

    def list(self, *, limit: int, cursor: str | None, dataset_mode: str) -> CandidatePage:
        if dataset_mode != "live":
            raise ValueError("live repository requires DATASET_MODE=live")
        if not self.display_enabled:
            return _empty_page(
                sources=self.sources,
                dataset_mode=dataset_mode,
                source_status="unavailable",
                warning="Public live display is disabled by runtime approval gates.",
            )
        if not self.acquisition.is_ready():
            return _empty_page(
                sources=self.sources,
                dataset_mode=dataset_mode,
                source_status="unavailable",
                warning="The live candidate store is unavailable.",
            )
        offset = _decode_live_cursor(cursor) if cursor else 0
        try:
            observations = self.acquisition.list_latest_observations(limit=limit + 1, offset=offset)
            total = self.acquisition.count_latest_observations()
            last_run = self.acquisition.latest_run(LIVE_SOURCE_ID)
            latest_artifact = self.acquisition.latest_artifact(LIVE_SOURCE_ID)
        except sa.exc.SQLAlchemyError:
            return _empty_page(
                sources=self.sources,
                dataset_mode=dataset_mode,
                source_status="error",
                warning="The live candidate store could not complete the request.",
            )
        if last_run is None or latest_artifact is None or not observations:
            return _empty_page(
                sources=self.sources,
                dataset_mode=dataset_mode,
                source_status="unknown",
                warning="No successful live candidate projection is available.",
            )
        if last_run.status not in {
            SourceRunStatus.SUCCEEDED,
            SourceRunStatus.SUCCEEDED_UNCHANGED,
            SourceRunStatus.PARTIAL,
        }:
            return _empty_page(
                sources=self.sources,
                dataset_mode=dataset_mode,
                source_status="error" if last_run.status is SourceRunStatus.FAILED else "unknown",
                warning="The latest live acquisition is not a successful candidate snapshot.",
                retrieved_at=latest_artifact.retrieved_at,
                record_count=last_run.records_fetched,
            )
        freshness = self.sources.freshness(LIVE_SOURCE_ID, last_run)
        partial = last_run.partial or last_run.status is SourceRunStatus.PARTIAL
        status = (
            "partial"
            if partial
            else "stale"
            if freshness.status is FreshnessStatus.STALE
            else "current"
        )
        has_more = len(observations) > limit
        visible = observations[:limit]
        items = tuple(
            _project_candidate(observation, rank=offset + index + 1)
            for index, observation in enumerate(visible)
        )
        source = self.sources.get(LIVE_SOURCE_ID)
        assert source is not None
        return CandidatePage(
            items=items,
            next_cursor=_encode_live_cursor(offset + limit) if has_more else None,
            total=total,
            dataset_mode="live",
            dataset_status=status,
            retrieved_at=latest_artifact.retrieved_at,
            published_at=None,
            stale_after=freshness.stale_after,
            partial=partial,
            sources=(
                CandidateSourceSummary(
                    id=source.id,
                    name=source.name,
                    status=("stale" if freshness.status is FreshnessStatus.STALE else "current"),
                    retrieved_at=latest_artifact.retrieved_at,
                    record_count=last_run.records_fetched,
                    detail=source.use_limitation,
                ),
            ),
            warnings=(
                source.use_limitation,
                "Assessor values are observations, not valuations, offers, or underwriting.",
                "Opportunity Zone membership is unverified pending a versioned spatial join.",
            ),
        )

    def get(self, candidate_id: UUID) -> CandidateReadModel | None:
        if not self.display_enabled:
            raise CandidateReadUnavailableError("Live candidate display is disabled.")
        if not self.acquisition.is_ready():
            raise CandidateReadUnavailableError("The live candidate store is unavailable.")
        # Detail lookups remain bounded for this screening slice.
        try:
            last_run = self.acquisition.latest_run(LIVE_SOURCE_ID)
            if last_run is None or last_run.status not in {
                SourceRunStatus.SUCCEEDED,
                SourceRunStatus.SUCCEEDED_UNCHANGED,
                SourceRunStatus.PARTIAL,
            }:
                raise CandidateReadUnavailableError(
                    "No successful live candidate projection is available."
                )
            observations = self.acquisition.list_latest_observations(limit=10_000)
        except CandidateReadUnavailableError:
            raise
        except sa.exc.SQLAlchemyError as error:
            raise CandidateReadUnavailableError(
                "The live candidate store could not complete the request."
            ) from error
        for rank, observation in enumerate(observations, start=1):
            candidate = _project_candidate(observation, rank=rank)
            if candidate.id == candidate_id:
                return candidate
        return None

    def is_ready(self) -> bool:
        return self.acquisition.is_ready()


def _project_candidate(
    observation: NormalizedParcelObservation,
    *,
    rank: int,
) -> CandidateReadModel:
    acreage = observation.tcad_acres or observation.gis_acres or 0.01
    display_name = observation.situs_address or f"TCAD parcel {observation.local_parcel_id}"
    locality = ", ".join(item for item in (observation.situs_city, "TX") if item)
    observed_values = tuple(
        value
        for value in (
            observation.appraised_value_cents,
            observation.market_value_cents,
            observation.land_value_cents,
        )
        if value is not None
    )
    display_dollars = (max(observed_values) // 100) if observed_values else 0
    # This is a deterministic research-queue score based only on completeness and acreage.
    completeness = sum(
        value is not None
        for value in (
            observation.geographic_id,
            observation.situs_address,
            observation.tcad_acres,
            observation.appraised_value_cents,
            observation.market_value_cents,
        )
    )
    screening_score = min(100.0, round(35 + completeness * 8 + min(acreage, 25), 1))
    candidate_id = uuid5(LIVE_CANDIDATE_NAMESPACE, observation.local_parcel_id)
    return CandidateReadModel(
        id=candidate_id,
        display_name=display_name,
        locality=locality or "Travis County, TX",
        parcel_id=f"TCAD-{observation.local_parcel_id}",
        candidate_kind=CandidateKind.PARCEL,
        parcel_count=1,
        jurisdiction_id=observation.jurisdiction_id,
        county_name="Travis County",
        state_name="Texas",
        timezone="America/Chicago",
        strategy="assessor",
        rank=rank,
        previous_rank=None,
        queue_state=CandidateQueueState.RESEARCH,
        opportunity_score=screening_score,
        confidence=min(1.0, round(0.3 + completeness * 0.1, 2)),
        acreage=acreage,
        value_range=MoneyRange(low=display_dollars, high=display_dollars),
        likely_basis=0,
        thesis=(
            "Deterministic assessor-screening result for the research queue; no investment, "
            "valuation, or offer recommendation is represented."
        ),
        opportunity_zone_status=OpportunityZoneStatus.REVIEW,
        next_action="Verify parcel identity, geometry, use limits, and Opportunity Zone overlay",
        evidence=EvidenceSummary(
            source_count=1,
            unresolved_conflict_count=0,
            freshness="current",
        ),
        as_of=observation.observed_at,
        screening_only=True,
        source_observation=SourceObservation(
            source_id=observation.source_id,
            source_record_id=observation.source_record_id,
            artifact_sha256=observation.artifact_sha256,
            retrieved_at=observation.observed_at,
            fields=SourceObservationFields(
                market_value_cents=observation.market_value_cents,
                appraised_value_cents=observation.appraised_value_cents,
                assessed_value_cents=observation.assessed_value_cents,
                land_value_cents=observation.land_value_cents,
                improvement_value_cents=observation.improvement_value_cents,
                acreage=acreage,
            ),
        ),
    )


def _empty_page(
    *,
    sources: InMemorySourceRegistry,
    dataset_mode: str,
    source_status: str,
    warning: str,
    retrieved_at: datetime | None = None,
    record_count: int | None = None,
) -> CandidatePage:
    source = sources.get(LIVE_SOURCE_ID)
    source_summaries = (
        (
            CandidateSourceSummary(
                id=source.id,
                name=source.name,
                status=source_status,
                retrieved_at=retrieved_at,
                record_count=record_count,
                detail=source.use_limitation,
            ),
        )
        if source is not None
        else ()
    )
    return CandidatePage(
        items=(),
        next_cursor=None,
        total=0,
        dataset_mode=dataset_mode,
        dataset_status="error",
        retrieved_at=retrieved_at,
        sources=source_summaries,
        warnings=(warning,),
    )


def _encode_live_cursor(offset: int) -> str:
    encoded = base64.urlsafe_b64encode(f"live:{READ_MODEL_VERSION}:{offset}".encode())
    return encoded.decode().rstrip("=")


def _decode_live_cursor(cursor: str) -> int:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        prefix, version, raw_offset = (
            base64.b64decode(padded, altchars=b"-_", validate=True).decode().rsplit(":", maxsplit=2)
        )
        offset = int(raw_offset)
    except (ValueError, UnicodeDecodeError) as error:
        raise InvalidCursorError("cursor is malformed") from error
    if prefix != "live" or version != READ_MODEL_VERSION or offset < 0:
        raise InvalidCursorError("cursor does not match this read-model version")
    return offset
