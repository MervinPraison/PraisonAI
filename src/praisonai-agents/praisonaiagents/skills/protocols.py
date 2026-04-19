"""Protocols for pluggable skill sources and invocation policies.

Core SDK stays protocol-driven (see AGENTS.md §4.1). These protocols let
wrappers or paid tiers plug in alternative skill storage (HTTP registry,
plugin bundle, enterprise policy) without touching the core.
"""

from __future__ import annotations

from typing import Protocol, Iterable, Optional, runtime_checkable

from .models import SkillProperties


@runtime_checkable
class SkillSourceProtocol(Protocol):
    """Abstract source of skills.

    Implementations may back skills onto the filesystem (default), an
    HTTP registry, a plugin directory, or an enterprise policy server.
    """

    def discover(self) -> Iterable[SkillProperties]:
        """Return every skill this source can supply."""
        ...

    def load_instructions(self, name: str) -> Optional[str]:
        """Return the SKILL.md body for ``name``, or None if unknown."""
        ...


@runtime_checkable
class SkillInvocationPolicyProtocol(Protocol):
    """Gatekeeps whether user/model can invoke a given skill."""

    def can_model_invoke(self, props: SkillProperties) -> bool:
        ...

    def can_user_invoke(self, props: SkillProperties) -> bool:
        ...
