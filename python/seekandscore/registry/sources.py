"""Source registry and freshness projection."""

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict

from seekandscore.acquisition.models import (
    AuthorityLevel,
    FreshnessStatus,
    SourceDescriptor,
    SourceRun,
    SourceRunStatus,
)

TRAVIS_TCAD_SOURCE = SourceDescriptor(
    id="travis_tcad_parcels",
    name="Travis County TNR / TCAD parcel layer",
    authority="Travis County Transportation and Natural Resources; source data from TCAD",
    authority_level=AuthorityLevel.OFFICIAL_DERIVATIVE,
    jurisdiction_id="us-tx-travis",
    capability="assessor_parcel",
    original_uri=(
        "https://gis.traviscountytx.gov/server1/rest/services/"
        "Boundaries_and_Jurisdictions/TCAD/MapServer/0"
    ),
    query_uri=(
        "https://gis.traviscountytx.gov/server1/rest/services/"
        "Boundaries_and_Jurisdictions/TCAD/MapServer/0/query"
    ),
    terms_uri="https://www.traviscountytx.gov/open-records",
    attribution_text="Travis Central Appraisal District; assembled by Travis County TNR",
    use_limitation=(
        "Informational/reference use only. Boundaries are approximate and not suitable for "
        "legal, engineering, or surveying purposes; accuracy and completeness are not warranted."
    ),
    cadence="monthly",
    freshness_days=45,
    geographic_vintage="current provider publication; exact publication date not exposed",
    adapter_version="travis-tcad-arcgis-v1",
    parser_version="travis-tcad-parcel-v1",
    display_allowed=False,
)


class SourceFreshness(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    status: FreshnessStatus
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    stale_after: datetime | None
    age_seconds: int | None
    last_run_status: SourceRunStatus | None


class InMemorySourceRegistry:
    """Descriptor registry; durable runs are loaded by repository adapters."""

    def __init__(self, sources: tuple[SourceDescriptor, ...] = (TRAVIS_TCAD_SOURCE,)) -> None:
        self._sources = {source.id: source for source in sources}
        if len(self._sources) != len(sources):
            raise ValueError("source identifiers must be unique")

    def get(self, source_id: str) -> SourceDescriptor | None:
        return self._sources.get(source_id)

    def list(self) -> tuple[SourceDescriptor, ...]:
        return tuple(self._sources.values())

    def freshness(
        self,
        source_id: str,
        last_run: SourceRun | None,
        *,
        now: datetime | None = None,
    ) -> SourceFreshness:
        source = self.get(source_id)
        if source is None:
            raise KeyError(source_id)
        current_time = now or datetime.now(UTC)
        if last_run is None:
            return SourceFreshness(
                source_id=source_id,
                status=FreshnessStatus.NEVER,
                last_attempt_at=None,
                last_success_at=None,
                stale_after=None,
                age_seconds=None,
                last_run_status=None,
            )
        successful = last_run.status in {
            SourceRunStatus.SUCCEEDED,
            SourceRunStatus.SUCCEEDED_UNCHANGED,
            SourceRunStatus.PARTIAL,
        }
        success_at = last_run.completed_at if successful else None
        if success_at is None:
            freshness = FreshnessStatus.UNKNOWN
            stale_after = None
            age_seconds = None
        else:
            stale_after = success_at + timedelta(days=source.freshness_days)
            freshness = (
                FreshnessStatus.CURRENT if current_time <= stale_after else FreshnessStatus.STALE
            )
            age_seconds = max(0, int((current_time - success_at).total_seconds()))
        return SourceFreshness(
            source_id=source_id,
            status=freshness,
            last_attempt_at=last_run.started_at,
            last_success_at=success_at,
            stale_after=stale_after,
            age_seconds=age_seconds,
            last_run_status=last_run.status,
        )

    def is_ready(self) -> bool:
        return bool(self._sources) and all(source.query_uri for source in self._sources.values())
