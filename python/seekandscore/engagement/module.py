"""Engagement bounded-context declaration."""

from seekandscore.kernel import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    name="engagement",
    owns=(
        "contact_points",
        "contact_permissions",
        "suppressions",
        "outreach_cases",
        "policy_decisions",
        "communications",
        "appointments",
        "information_requests",
    ),
)
