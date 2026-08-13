"""Bounded-context registry and projection tests."""

from seekandscore.bootstrap import MODULES
from seekandscore.readmodels import SyntheticCandidateRepository
from seekandscore.registry import InMemoryGeographyRegistry


def test_module_ownership_is_declared_and_unique() -> None:
    assert [module.name for module in MODULES] == [
        "platform",
        "registry",
        "identity",
        "engagement",
    ]
    assert len({module.name for module in MODULES}) == len(MODULES)
    assert all(module.owns for module in MODULES)


def test_synthetic_projection_is_deterministic() -> None:
    first = SyntheticCandidateRepository(InMemoryGeographyRegistry())
    second = SyntheticCandidateRepository(InMemoryGeographyRegistry())

    first_page = first.list(limit=25, cursor=None, dataset_mode="synthetic")
    second_page = second.list(limit=25, cursor=None, dataset_mode="synthetic")

    assert first_page == second_page
