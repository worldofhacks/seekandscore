"""Composition root for the modular monolith."""

from dataclasses import dataclass

from seekandscore.engagement import EngagementSafetyStatus
from seekandscore.engagement.module import DESCRIPTOR as ENGAGEMENT_DESCRIPTOR
from seekandscore.identity.module import DESCRIPTOR as IDENTITY_DESCRIPTOR
from seekandscore.kernel import ModuleDescriptor
from seekandscore.platform.module import DESCRIPTOR as PLATFORM_DESCRIPTOR
from seekandscore.platform.settings import Settings
from seekandscore.readmodels import SyntheticCandidateRepository
from seekandscore.registry import InMemoryGeographyRegistry
from seekandscore.registry.module import DESCRIPTOR as REGISTRY_DESCRIPTOR

MODULES: tuple[ModuleDescriptor, ...] = (
    PLATFORM_DESCRIPTOR,
    REGISTRY_DESCRIPTOR,
    IDENTITY_DESCRIPTOR,
    ENGAGEMENT_DESCRIPTOR,
)


@dataclass(frozen=True, slots=True)
class AppContainer:
    """Explicit dependencies shared by API and process entrypoints."""

    settings: Settings
    geography: InMemoryGeographyRegistry
    candidates: SyntheticCandidateRepository
    engagement: EngagementSafetyStatus

    @classmethod
    def build(cls, settings: Settings) -> "AppContainer":
        geography = InMemoryGeographyRegistry()
        return cls(
            settings=settings,
            geography=geography,
            candidates=SyntheticCandidateRepository(geography),
            engagement=EngagementSafetyStatus.from_settings(settings),
        )

    def readiness_checks(self) -> dict[str, bool]:
        return {
            "configuration": True,
            "registry": self.geography.is_ready(),
            "candidate_read_model": self.candidates.is_ready(),
            "engagement_guard": self.engagement.is_safe,
        }
