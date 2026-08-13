"""Rebuildable projections composed from bounded-context contracts."""

from seekandscore.readmodels.candidates import (
    CandidatePage,
    CandidateReadModel,
    SyntheticCandidateRepository,
)
from seekandscore.readmodels.live_candidates import LiveCandidateRepository

__all__ = [
    "CandidatePage",
    "CandidateReadModel",
    "LiveCandidateRepository",
    "SyntheticCandidateRepository",
]
