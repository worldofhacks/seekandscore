"""Geospatial enrichment bounded-context descriptor."""

from seekandscore.kernel import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    name="geography",
    owns=(
        "OpportunityZoneRound",
        "OpportunityZoneTract",
        "OpportunityZoneImportRun",
        "parcel_layer_memberships",
    ),
)
