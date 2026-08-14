"""Composition root for the modular monolith."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa

from seekandscore.acquisition.module import DESCRIPTOR as ACQUISITION_DESCRIPTOR
from seekandscore.acquisition.repository import (
    AcquisitionRepository,
    PostgresAcquisitionRepository,
)
from seekandscore.deal.module import DESCRIPTOR as DEAL_DESCRIPTOR
from seekandscore.deal.repository import PostgresResearchCaseRepository
from seekandscore.deal.service import ResearchCaseService
from seekandscore.engagement import EngagementSafetyStatus
from seekandscore.engagement.module import DESCRIPTOR as ENGAGEMENT_DESCRIPTOR
from seekandscore.geography.module import DESCRIPTOR as GEOGRAPHY_DESCRIPTOR
from seekandscore.identity.module import DESCRIPTOR as IDENTITY_DESCRIPTOR
from seekandscore.kernel import ModuleDescriptor
from seekandscore.platform.module import DESCRIPTOR as PLATFORM_DESCRIPTOR
from seekandscore.platform.settings import Settings
from seekandscore.readmodels import LiveCandidateRepository, UnavailableCandidateRepository
from seekandscore.readmodels.candidates import CandidatePage, CandidateReadModel
from seekandscore.registry import InMemoryGeographyRegistry, InMemorySourceRegistry
from seekandscore.registry.module import DESCRIPTOR as REGISTRY_DESCRIPTOR
from seekandscore.registry.sources import TRAVIS_TCAD_DISPLAY_APPROVAL_ID

MODULES: tuple[ModuleDescriptor, ...] = (
    PLATFORM_DESCRIPTOR,
    REGISTRY_DESCRIPTOR,
    IDENTITY_DESCRIPTOR,
    GEOGRAPHY_DESCRIPTOR,
    ENGAGEMENT_DESCRIPTOR,
    DEAL_DESCRIPTOR,
    ACQUISITION_DESCRIPTOR,
)


class CandidateRepository(Protocol):
    serving_mode: str
    display_enabled: bool

    def list(
        self,
        *,
        limit: int,
        cursor: str | None,
        dataset_mode: str,
        q: str | None = None,
        city: str | None = None,
        min_acres: float | None = None,
        max_acres: float | None = None,
    ) -> CandidatePage: ...

    def get(self, candidate_id: UUID) -> CandidateReadModel | None: ...

    def is_ready(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class AppContainer:
    """Explicit dependencies shared by API and process entrypoints."""

    settings: Settings
    geography: InMemoryGeographyRegistry
    candidates: CandidateRepository
    sources: InMemorySourceRegistry
    source_runs: AcquisitionRepository | None
    research: ResearchCaseService | None
    engagement: EngagementSafetyStatus

    @classmethod
    def build(cls, settings: Settings) -> "AppContainer":
        geography = InMemoryGeographyRegistry()
        sources = InMemorySourceRegistry()
        source_runs: AcquisitionRepository | None = None
        research: ResearchCaseService | None = None
        if settings.database_url:
            engine = sa.create_engine(settings.database_url, pool_pre_ping=True)
            source_runs = PostgresAcquisitionRepository(engine)
            research = ResearchCaseService(PostgresResearchCaseRepository(engine))
        if settings.dataset_mode == "live" and source_runs is not None:
            live_source = sources.get("travis_tcad_parcels")
            candidates: CandidateRepository = LiveCandidateRepository(
                source_runs,
                sources,
                display_enabled=bool(
                    settings.live_source_display_enabled
                    and settings.live_source_display_approval_id == TRAVIS_TCAD_DISPLAY_APPROVAL_ID
                    and live_source is not None
                    and live_source.display_allowed
                ),
            )
        else:
            reason = (
                "Candidate serving requires DATASET_MODE=live."
                if settings.dataset_mode != "live"
                else "The live candidate store is not configured."
            )
            candidates = UnavailableCandidateRepository(sources, reason=reason)
        return cls(
            settings=settings,
            geography=geography,
            candidates=candidates,
            sources=sources,
            source_runs=source_runs,
            research=research,
            engagement=EngagementSafetyStatus.from_settings(settings),
        )

    def readiness_checks(self) -> dict[str, bool]:
        return {
            "configuration": True,
            "registry": self.geography.is_ready(),
            "source_registry": self.sources.is_ready(),
            "candidate_read_model": self.candidates.is_ready(),
            "research_store": (
                self.research is not None and self.research.is_ready()
                if self.settings.research_writes_enabled
                else True
            ),
            "engagement_guard": self.engagement.is_safe,
        }
