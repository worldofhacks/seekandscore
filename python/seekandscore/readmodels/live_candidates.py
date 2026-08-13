"""Internal assessor-screen projection built from latest source observations."""

import base64
from datetime import datetime
from uuid import UUID, uuid5

import sqlalchemy as sa

from seekandscore.acquisition.models import (
    FreshnessStatus,
    NormalizedParcelObservation,
    SourceRunProfile,
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
from seekandscore.registry.sources import TRAVIS_TCAD_AUTHORIZED_CITIES
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
            latest_attempt = self.acquisition.latest_run(LIVE_SOURCE_ID)
            last_run = self.acquisition.latest_complete_run(
                LIVE_SOURCE_ID, run_profile=SourceRunProfile.COHORT
            )
        except sa.exc.SQLAlchemyError:
            return _empty_page(
                sources=self.sources,
                dataset_mode=dataset_mode,
                source_status="error",
                warning="The live candidate store could not complete the request.",
            )
        if last_run is None:
            return _empty_page(
                sources=self.sources,
                dataset_mode=dataset_mode,
                source_status="unknown",
                warning="No complete approved live cohort is available.",
            )
        try:
            observations = self.acquisition.list_latest_observations(
                limit=limit + 1,
                offset=offset,
                artifact_ids=last_run.artifact_ids,
                cities=TRAVIS_TCAD_AUTHORIZED_CITIES,
            )
            total = self.acquisition.count_latest_observations(
                artifact_ids=last_run.artifact_ids,
                cities=TRAVIS_TCAD_AUTHORIZED_CITIES,
            )
            latest_artifact = self.acquisition.latest_artifact(
                LIVE_SOURCE_ID, artifact_ids=last_run.artifact_ids
            )
        except sa.exc.SQLAlchemyError:
            return _empty_page(
                sources=self.sources,
                dataset_mode=dataset_mode,
                source_status="error",
                warning="The live candidate store could not complete the request.",
                retrieved_at=last_run.retrieved_at,
                record_count=last_run.records_fetched,
            )
        if latest_artifact is None or not observations:
            return _empty_page(
                sources=self.sources,
                dataset_mode=dataset_mode,
                source_status="unknown",
                warning="The complete cohort has no publishable parcel observations.",
                retrieved_at=last_run.retrieved_at,
                record_count=last_run.records_fetched,
            )
        freshness = self.sources.freshness(LIVE_SOURCE_ID, last_run)
        failed_refresh = bool(
            latest_attempt is not None
            and latest_attempt.run_profile is SourceRunProfile.COHORT
            and latest_attempt.id != last_run.id
            and not latest_attempt.is_complete_cohort
        )
        status = (
            "stale" if failed_refresh or freshness.status is FreshnessStatus.STALE else "current"
        )
        source_status = (
            "error"
            if failed_refresh
            else "stale"
            if freshness.status is FreshnessStatus.STALE
            else "current"
        )
        retrieved_at = last_run.retrieved_at or latest_artifact.retrieved_at
        has_more = len(observations) > limit
        visible = observations[:limit]
        items = tuple(
            _project_candidate(
                observation,
                rank=offset + index + 1,
                retrieved_at=retrieved_at,
            )
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
            retrieved_at=retrieved_at,
            published_at=None,
            stale_after=freshness.stale_after,
            partial=False,
            sources=(
                CandidateSourceSummary(
                    id=source.id,
                    name=source.name,
                    status=source_status,
                    retrieved_at=retrieved_at,
                    record_count=last_run.records_fetched,
                    detail=source.use_limitation,
                ),
            ),
            warnings=(
                *(
                    ("The latest cohort refresh failed; this is the last complete snapshot.",)
                    if failed_refresh
                    else ()
                ),
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
            last_run = self.acquisition.latest_complete_run(
                LIVE_SOURCE_ID, run_profile=SourceRunProfile.COHORT
            )
            if last_run is None:
                raise CandidateReadUnavailableError(
                    "No complete approved cohort projection is available."
                )
            observations = self.acquisition.list_latest_observations(
                limit=10_000,
                artifact_ids=last_run.artifact_ids,
                cities=TRAVIS_TCAD_AUTHORIZED_CITIES,
            )
        except CandidateReadUnavailableError:
            raise
        except sa.exc.SQLAlchemyError as error:
            raise CandidateReadUnavailableError(
                "The live candidate store could not complete the request."
            ) from error
        for rank, observation in enumerate(observations, start=1):
            candidate = _project_candidate(
                observation,
                rank=rank,
                retrieved_at=last_run.retrieved_at or observation.observed_at,
            )
            if candidate.id == candidate_id:
                return candidate
        return None

    def is_ready(self) -> bool:
        return self.acquisition.is_ready()


def _project_candidate(
    observation: NormalizedParcelObservation,
    *,
    rank: int,
    retrieved_at: datetime,
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
        as_of=retrieved_at,
        screening_only=True,
        source_observation=SourceObservation(
            source_id=observation.source_id,
            source_record_id=observation.source_record_id,
            artifact_sha256=observation.artifact_sha256,
            retrieved_at=retrieved_at,
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
