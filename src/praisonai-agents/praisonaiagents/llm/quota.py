"""
Provider Quota Coordination for PraisonAI Agents.

Provides a lightweight, protocol-driven seam so provider-quota state
(credential cooldowns / benches) can be coordinated *fleet-wide* when a
shared backend is configured, while defaulting to today's in-process,
in-memory behaviour with zero new dependencies and no hot-path change.

Design:
- ``QuotaCoordinatorProtocol`` is a pure contract (stdlib + typing only).
- ``LocalQuotaCoordinator`` is the default in-memory implementation used
  when no shared backend is selected — single-replica deployments behave
  exactly as before.
- A concrete shared backend (e.g. Redis, reusing the gateway's existing
  connection) implements the same protocol in the wrapper/bot package and
  is selected via ``QuotaCoordinatorConfig``. Core keeps only the protocol
  and the in-memory default.

Fail-open by contract: implementations MUST degrade to local behaviour on
backend errors rather than wedge a healthy request path, and bench entries
carry TTLs so a dead replica's benches self-expire.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class QuotaCoordinatorProtocol(Protocol):
    """Contract for coordinating provider-quota state across replicas.

    A coordinator tracks per-credential cooldowns ("benches"). When a shared
    backend is configured, a credential benched by any replica is treated as
    benched by all replicas until its cooldown expires.
    """

    def bench(self, cred_id: str, *, until: float, reason: str = "") -> None:
        """Bench a credential until ``until`` (an epoch timestamp, TTL-based)."""
        ...

    def is_benched(self, cred_id: str, *, now: Optional[float] = None) -> bool:
        """Return True if the credential is currently benched."""
        ...

    def benched_until(self, cred_id: str, *, now: Optional[float] = None) -> Optional[float]:
        """Return the epoch timestamp the credential is benched until, or None."""
        ...

    def clear(self, cred_id: str) -> None:
        """Clear any bench for the credential (e.g. on recovery)."""
        ...


@dataclass
class QuotaCoordinatorConfig:
    """Configuration for provider-quota coordination.

    Attributes:
        backend: ``"local"`` (in-memory, default) or a shared backend name
            such as ``"redis"`` provided by the wrapper/bot package.
        url: Optional backend URL; when omitted a shared backend reuses the
            already-established connection (e.g. gateway ``RedisConfig``).
    """

    backend: str = "local"
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {"backend": self.backend, "url": self.url}

    @classmethod
    def from_dict(cls, data: Dict[str, Optional[str]]) -> "QuotaCoordinatorConfig":
        return cls(
            backend=(data.get("backend") or "local"),
            url=data.get("url"),
        )


class LocalQuotaCoordinator:
    """In-memory ``QuotaCoordinatorProtocol`` (default, zero-dependency).

    Thread-safe via a lightweight lock. Bench entries carry an expiry so
    they self-clear once the cooldown passes — mirroring the TTL semantics a
    shared backend uses so behaviour is identical across implementations.
    """

    def __init__(self) -> None:
        import threading

        self._benches: Dict[str, float] = {}
        self._lock = threading.Lock()

    def bench(self, cred_id: str, *, until: float, reason: str = "") -> None:
        with self._lock:
            existing = self._benches.get(cred_id)
            # Keep the longest cooldown if a longer one is already set.
            if existing is None or until > existing:
                self._benches[cred_id] = until

    def is_benched(self, cred_id: str, *, now: Optional[float] = None) -> bool:
        return self.benched_until(cred_id, now=now) is not None

    def benched_until(self, cred_id: str, *, now: Optional[float] = None) -> Optional[float]:
        current = time.time() if now is None else now
        with self._lock:
            until = self._benches.get(cred_id)
            if until is None:
                return None
            if current >= until:
                # Expired — self-clear.
                self._benches.pop(cred_id, None)
                return None
            return until

    def clear(self, cred_id: str) -> None:
        with self._lock:
            self._benches.pop(cred_id, None)


def build_quota_coordinator(
    config: Optional[QuotaCoordinatorConfig] = None,
) -> QuotaCoordinatorProtocol:
    """Build a coordinator from config, defaulting to the local in-memory one.

    Only the ``"local"`` backend is resolvable from core. Shared backends
    (e.g. ``"redis"``) are provided by the wrapper/bot package, which passes
    an already-constructed coordinator instance to ``FailoverManager``; this
    helper falls back to local for unknown backends so core never grows a
    heavy optional dependency.
    """
    if config is None or config.backend == "local":
        return LocalQuotaCoordinator()
    # Unknown/heavy backend not resolvable in core: fail open to local.
    return LocalQuotaCoordinator()
