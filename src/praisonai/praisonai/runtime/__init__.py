"""
Warm local runtime for PraisonAI.

An opt-in, long-lived local process that keeps provider clients, MCP
connections and recent session/context warm so repeated ``praisonai run``
invocations don't pay cold-start cost.

The thin CLI attaches to a running runtime when present (via a loopback
HTTP transport described by a lockfile) and falls back to in-process
execution when it is not. Nothing here is imported eagerly by the core
SDK — it is wrapper-layer deployment/UX infrastructure.

Public surface:
- :class:`RuntimeDescriptor` — lockfile read/write for an active runtime.
- :func:`get_runtime_descriptor` — load the descriptor for this project.
- :class:`RuntimeClient` — thin client used by ``run`` to forward a prompt.
"""

from .descriptor import (
    RuntimeDescriptor,
    get_runtime_descriptor,
    get_runtime_lock_path,
    get_runtime_version,
    versions_compatible,
)
from .client import RuntimeClient, RuntimeUnavailable

__all__ = [
    "RuntimeDescriptor",
    "get_runtime_descriptor",
    "get_runtime_lock_path",
    "get_runtime_version",
    "versions_compatible",
    "RuntimeClient",
    "RuntimeUnavailable",
]
