"""Acquisition bounded-context declaration."""

from seekandscore.kernel import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    name="acquisition",
    owns=(
        "raw_artifacts",
        "source_records",
        "normalized_observations",
        "quarantine_records",
    ),
)
