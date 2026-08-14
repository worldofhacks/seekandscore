"""Bounded-context registry tests."""

from seekandscore.bootstrap import MODULES
from seekandscore.registry import InMemoryGeographyRegistry


def test_module_ownership_is_declared_and_unique() -> None:
    assert [module.name for module in MODULES] == [
        "platform",
        "registry",
        "identity",
        "geography",
        "engagement",
        "deal",
        "acquisition",
    ]
    assert len({module.name for module in MODULES}) == len(MODULES)
    assert all(module.owns for module in MODULES)


def test_launch_geography_reference_data_is_deterministic() -> None:
    first = InMemoryGeographyRegistry()
    second = InMemoryGeographyRegistry()

    assert first.get("us-tx-travis") == second.get("us-tx-travis")
    assert first.get("us-tx-bastrop").county_fips == "021"  # type: ignore[union-attr]
    assert first.get("us-tx-caldwell").county_fips == "055"  # type: ignore[union-attr]
