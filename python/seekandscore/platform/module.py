"""Platform bounded-context declaration."""

from seekandscore.kernel import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    name="platform",
    owns=(
        "organizations",
        "users",
        "roles",
        "feature_flags",
        "audit_events",
        "outbox",
    ),
)
