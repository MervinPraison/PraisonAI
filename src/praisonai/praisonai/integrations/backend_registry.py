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

import logging
import threading
from typing import Type

from .._registry import PluginRegistry

logger = logging.getLogger(__name__)


def _anthropic_loader() -> Type:
    from .managed_agents import AnthropicManagedAgent
    return AnthropicManagedAgent


# Compute places that cannot host a whole agent loop, so they are never
# registered as managed backends: `ssh` needs an object rather than a name;
# `local`/`native`/`subprocess` would run the agent in your own shell (which is
# what you get by passing nothing); `sandlock` isolates tools rather than
# hosting a runtime.
_COMPUTE_SKIP = {"ssh", "local", "native", "subprocess", "sandlock"}


_BUILTIN_BACKENDS = {
    "anthropic": _anthropic_loader,
    # Compute-backed loaders (docker + every other compute place able to host a
    # whole agent loop) are registered lazily inside the registry -- see
    # ``_ensure_compute_registered`` -- so a bare import of this module pays
    # nothing: no entry-point walk, no core-SDK import, no closure minting.
}


class ManagedBackendRegistry(PluginRegistry):
    """Registry for managed agent-runtime backends with entry-point support."""

    def __init__(self) -> None:
        super().__init__(
            entry_point_group="praisonai.managed_backends",
            builtins=_BUILTIN_BACKENDS,
        )
        self._compute_registered = False
        self._compute_lock = threading.Lock()

    def _ensure_compute_registered(self) -> None:
        """Discover compute-backed backends on first lookup, not at import.

        ``run_on=`` accepted two names while ``tools_run_on=`` accepted twelve,
        which was an implementation detail leaking into the vocabulary: a place
        that can run a command can run the agent loop, which is just one more
        command. One generic backend covers them all. `docker` used to be
        excluded here in favour of a bespoke backend, but that named its
        containers in a shape ``DockerCompute``'s lookup did not recognise, so
        the generic path is used for reclaim.

        The probe (an entry-point walk plus a core-SDK import) runs at most once
        and only when a backend is actually requested by name.
        """
        if self._compute_registered:
            return
        with self._compute_lock:
            if self._compute_registered:
                return
            try:
                from .compute_managed_agent import make_loader
                from praisonaiagents.managed._compute_bridge import (
                    available_providers,
                )

                for name in available_providers():
                    if name in _COMPUTE_SKIP or name in _BUILTIN_BACKENDS:
                        continue
                    self._add_loader(name, make_loader(name))
            except Exception:
                # A broken/absent compute plugin must not be silently invisible.
                logger.debug(
                    "compute backend discovery failed; falling back to the "
                    "anthropic-only registry",
                    exc_info=True,
                )
            self._compute_registered = True

    def resolve(self, name: str) -> Type:
        self._ensure_compute_registered()
        return super().resolve(name)

    def list_names(self) -> list[str]:
        self._ensure_compute_registered()
        return super().list_names()

    def has(self, name: str) -> bool:
        self._ensure_compute_registered()
        return super().has(name)


def get_backend_registry() -> "ManagedBackendRegistry":
    """Return the process-default managed-backend registry."""
    return ManagedBackendRegistry.default()
