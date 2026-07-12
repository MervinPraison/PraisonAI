"""Harness profiles and the model-family resolver.

A :class:`HarnessProfile` bundles two family-tuned knobs:

* ``base_prompt`` — an optional system-prompt fragment prepended to the
  assembled prompt with family-specific tool-use guidance.
* ``preferred_edit_format`` — the file-edit primitive the family handles
  best (``"apply_patch"`` or ``"edit_file"``); ``None`` keeps the current
  both-exposed behaviour.

The registry maps case-insensitive substring matchers (evaluated against the
model id) to profiles. Unknown models fall back to :data:`DEFAULT_PROFILE`,
which is behaviour-preserving (no prompt fragment, no edit-format preference).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:  # Python 3.8+ Protocol lives in typing; fall back for older interpreters.
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover - defensive
    from typing_extensions import Protocol, runtime_checkable  # type: ignore


@dataclass(frozen=True)
class HarnessProfile:
    """A model-family harness profile.

    Attributes:
        name: Identifier for the profile (e.g. ``"default"``, ``"anthropic"``).
        base_prompt: Optional prompt fragment prepended to the system prompt.
            ``None`` means no fragment (behaviour-preserving default).
        preferred_edit_format: Preferred edit primitive name, or ``None`` to
            keep exposing both primitives in their current order.
    """

    name: str = "default"
    base_prompt: Optional[str] = None
    preferred_edit_format: Optional[str] = None


@runtime_checkable
class HarnessResolverProtocol(Protocol):
    """Protocol for objects that resolve a model id to a harness profile."""

    def resolve_harness(self, model: Optional[str]) -> HarnessProfile:
        ...


# Behaviour-preserving default: no fragment, no edit-format preference.
DEFAULT_PROFILE = HarnessProfile(name="default")


# Family matchers: (list of case-insensitive substrings, profile).
# Ordered; first match wins. Kept intentionally small and data-driven so
# consumers can extend/override via register_profile().
_DEFAULT_REGISTRY: List[Tuple[List[str], HarnessProfile]] = [
    (
        ["claude", "anthropic"],
        HarnessProfile(
            name="anthropic",
            base_prompt=(
                "When editing files, prefer patch-style edits: use apply_patch "
                "to create or rewrite files and edit_file for targeted changes."
            ),
            preferred_edit_format="apply_patch",
        ),
    ),
    (
        ["gpt", "openai", "o1", "o3", "o4"],
        HarnessProfile(
            name="openai",
            base_prompt=(
                "When editing files, prefer targeted string-replacement edits: "
                "use edit_file to modify existing files precisely."
            ),
            preferred_edit_format="edit_file",
        ),
    ),
]

_registry_lock = threading.RLock()
_registry: List[Tuple[List[str], HarnessProfile]] = list(_DEFAULT_REGISTRY)


def register_profile(matchers: List[str], profile: HarnessProfile) -> None:
    """Register (or prepend) a family matcher → profile mapping.

    New registrations take precedence over the built-in defaults so callers
    can override behaviour. Thread-safe.

    Args:
        matchers: Case-insensitive substrings matched against the model id.
        profile: The :class:`HarnessProfile` to resolve when a matcher hits.
    """
    normalized = [m.lower() for m in matchers if m]
    with _registry_lock:
        _registry.insert(0, (normalized, profile))


def resolve_harness(model: Optional[str]) -> HarnessProfile:
    """Resolve a model id to a :class:`HarnessProfile`.

    Unknown / falsy models return :data:`DEFAULT_PROFILE` (no behaviour change).

    Args:
        model: The model id string (e.g. ``"claude-opus-4"``).

    Returns:
        The first matching profile, or the default profile.
    """
    if not model:
        return DEFAULT_PROFILE
    lowered = model.lower()
    with _registry_lock:
        for matchers, profile in _registry:
            if any(m in lowered for m in matchers):
                return profile
    return DEFAULT_PROFILE
