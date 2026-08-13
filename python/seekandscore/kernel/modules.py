"""Bounded-context metadata used for startup and readiness checks."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModuleDescriptor:
    """Declares a context's stable name and the records it owns."""

    name: str
    owns: tuple[str, ...]
    ready: bool = True
