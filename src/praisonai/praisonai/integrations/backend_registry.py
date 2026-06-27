"""Registry of managed agent-runtime backends.

This moves provider -> backend resolution off the hardcoded ``if provider !=
"anthropic"`` switch in :mod:`hosted_agent` and onto the same plugin-registry
primitive used for framework adapters. A third-party package can register a
``praisonai.managed_backends`` entry point and have ``HostedAgent(provider=...)``
resolve it with no core change.

Builtins:
    - ``anthropic`` -> :class:`AnthropicManagedAgent`

Future entry-point backends (e.g. ``e2b``, ``modal``, ``flyio``) register
themselves under the ``praisonai.managed_backends`` group.
"""

from __future__ import annotations

from typing import Type

from .._registry import PluginRegistry


def _anthropic_loader() -> Type:
    from .managed_agents import AnthropicManagedAgent
    return AnthropicManagedAgent


_BUILTIN_BACKENDS = {
    "anthropic": _anthropic_loader,
}


class ManagedBackendRegistry(PluginRegistry):
    """Registry for managed agent-runtime backends with entry-point support."""

    def __init__(self) -> None:
        super().__init__(
            entry_point_group="praisonai.managed_backends",
            builtins=_BUILTIN_BACKENDS,
        )


def get_backend_registry() -> "ManagedBackendRegistry":
    """Return the process-default managed-backend registry."""
    return ManagedBackendRegistry.default()
