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
from seekandscore.engagement import EngagementSafetyStatus
from seekandscore.engagement.module import DESCRIPTOR as ENGAGEMENT_DESCRIPTOR
from seekandscore.identity.module import DESCRIPTOR as IDENTITY_DESCRIPTOR
from seekandscore.kernel import ModuleDescriptor
from seekandscore.platform.module import DESCRIPTOR as PLATFORM_DESCRIPTOR
from seekandscore.platform.settings import Settings
from seekandscore.readmodels import LiveCandidateRepository, SyntheticCandidateRepository
from seekandscore.readmodels.candidates import CandidatePage, CandidateReadModel
from seekandscore.registry import InMemoryGeographyRegistry, InMemorySourceRegistry
from seekandscore.registry.module import DESCRIPTOR as REGISTRY_DESCRIPTOR

MODULES: tuple[ModuleDescriptor, ...] = (
    PLATFORM_DESCRIPTOR,
    REGISTRY_DESCRIPTOR,
    IDENTITY_DESCRIPTOR,
    ENGAGEMENT_DESCRIPTOR,
    ACQUISITION_DESCRIPTOR,
)


class CandidateRepository(Protocol):
    def list(self, *, limit: int, cursor: str | None, dataset_mode: str) -> CandidatePage: ...

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
    engagement: EngagementSafetyStatus

    @classmethod
    def build(cls, settings: Settings) -> "AppContainer":
        geography = InMemoryGeographyRegistry()
        sources = InMemorySourceRegistry()
        source_runs: AcquisitionRepository | None = None
        if settings.database_url:
            source_runs = PostgresAcquisitionRepository(
                sa.create_engine(settings.database_url, pool_pre_ping=True)
            )
        if settings.dataset_mode == "live" and source_runs is not None:
            live_source = sources.get("travis_tcad_parcels")
            candidates: CandidateRepository = LiveCandidateRepository(
                source_runs,
                sources,
                display_enabled=bool(
                    settings.live_source_display_enabled
                    and live_source is not None
                    and live_source.display_allowed
                ),
            )
        else:
            candidates = SyntheticCandidateRepository(geography)
        return cls(
            settings=settings,
            geography=geography,
            candidates=candidates,
            sources=sources,
            source_runs=source_runs,
            engagement=EngagementSafetyStatus.from_settings(settings),
        )

    def readiness_checks(self) -> dict[str, bool]:
        return {
            "configuration": True,
            "registry": self.geography.is_ready(),
            "source_registry": self.sources.is_ready(),
            "candidate_read_model": self.candidates.is_ready(),
            "engagement_guard": self.engagement.is_safe,
        }
