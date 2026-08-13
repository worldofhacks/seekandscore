"""Registry bounded-context declaration."""

from seekandscore.kernel import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    name="registry",
    owns=(
        "jurisdictions",
        "geography_versions",
        "region_packs",
        "source_definitions",
        "source_policies",
        "adapter_versions",
        "source_runs",
        "source_freshness",
    ),
)
