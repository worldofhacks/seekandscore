"""Deal-operations bounded-context descriptor."""

from seekandscore.kernel import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    name="deal",
    owns=(
        "ResearchCase",
        "ResearchCaseRevision",
        "CandidateDossier",
        "VerificationGate",
    ),
)
