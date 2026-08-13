"""Identity bounded-context declaration."""

from seekandscore.kernel import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    name="identity",
    owns=(
        "parcels",
        "parcel_identifiers",
        "parcel_lineage",
        "investment_candidates",
        "entities",
        "ownership_interests",
        "property_party_assignments",
    ),
)
