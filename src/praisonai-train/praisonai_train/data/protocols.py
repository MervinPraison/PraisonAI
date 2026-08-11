"""Protocols for the pluggable data layer.

Every recipe and QC check implements one of these; the generator and scorer
depend only on the protocol, never on concrete classes (dependency inversion).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

# A prompt spec is {"system": str, "user": str}. A row is {instruction,input,output}.


@runtime_checkable
class Recipe(Protocol):
    """Describes a synthetic-data domain: how to build diverse teacher prompts."""

    name: str

    def prompts(self, n: int, start: int = 0) -> list[dict]:
        """Deterministically fan out n prompt specs starting at index ``start``
        (disjoint offsets let parallel workers avoid overlap)."""
        ...


@runtime_checkable
class RowCheck(Protocol):
    """A single per-row quality check. ``kind`` is 'drop' or 'flag'."""

    name: str
    kind: str

    def triggered(self, instruction: str, input: str, output: str, cfg: dict) -> bool:
        """Return True if this row trips the check."""
        ...
