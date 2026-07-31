"""
Unified degraded-capability registry for the gateway (Issue #3518).

The gateway records degradation in several disconnected places but historically
exposed only *degraded channels* through ``health()``. Provider/model credential
failures, unresolved ``SecretRef`` capabilities, and route-level failures were
classified-but-not-surfaced or not surfaced at all — a partial degraded state
where some failures are effectively invisible until a message silently goes
nowhere.

This module provides one small, process-local contract that any owner records
into at the boundary that owns it, so ``gateway status`` / ``gateway doctor`` /
``health()`` can list *every* degraded owner with a consistent, redacted shape
and an actionable next step. It is a generic protocol + default in-process impl
with no heavy third-party imports, mirroring the existing gateway
policy-protocol + default-impl pattern in ``protocols.py``.

Owners call :meth:`DegradedCapabilityRegistry.mark` when they enter a degraded
state and :meth:`DegradedCapabilityRegistry.clear` on recovery; readers call
:meth:`DegradedCapabilityRegistry.list_degraded`.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, List, Protocol, Tuple, runtime_checkable

# Closed vocabularies kept as module constants so owners and readers agree on
# the shape without importing an enum-heavy dependency.
OWNER_KINDS: Tuple[str, ...] = ("channel", "provider", "capability", "route", "gateway")
DEGRADED_STATES: Tuple[str, ...] = ("cold", "stale")


@dataclass(frozen=True)
class DegradedOwner:
    """A single degraded owner, redacted and operator-safe.

    Attributes:
        owner_kind: One of ``channel | provider | capability | route | gateway``.
        owner_id: Stable identity, e.g. ``telegram:main``, ``openai``, ``mcp:notion``.
        state: ``cold`` (no last-known-good) or ``stale`` (reusing last-known-good).
        reason: Redacted, operator-safe explanation — never leaks token/secret material.
        retry_hint: The exact next action, and it MUST name a command that
            exists — e.g. ``praisonai gateway doctor --fix`` (implemented in the
            wrapper CLI as a detect → repair → re-validate loop). Never point an
            operator at a non-existent command.
    """

    owner_kind: str
    owner_id: str
    state: str
    reason: str
    retry_hint: str = ""

    def __post_init__(self) -> None:
        # Enforce the closed vocabularies at construction so an unsupported
        # owner_kind/state can never reach an operator-facing record. Frozen
        # dataclass validation belongs here rather than being duplicated by
        # every writer and reader (Issue #3518).
        if self.owner_kind not in OWNER_KINDS:
            raise ValueError(
                f"owner_kind {self.owner_kind!r} not in {OWNER_KINDS!r}"
            )
        if self.state not in DEGRADED_STATES:
            raise ValueError(
                f"state {self.state!r} not in {DEGRADED_STATES!r}"
            )

    def to_dict(self) -> Dict[str, str]:
        return {
            "owner_kind": self.owner_kind,
            "owner_id": self.owner_id,
            "state": self.state,
            "reason": self.reason,
            "retry_hint": self.retry_hint,
        }


@runtime_checkable
class DegradedCapabilityProtocol(Protocol):
    """Contract every degraded-capability registry implements.

    Owners write facts where they happen (``mark``/``clear``); readers
    (``health()``, ``gateway status``/``doctor``) read them where needed
    (``list_degraded``).
    """

    def mark(self, owner: DegradedOwner) -> None: ...

    def clear(self, owner_kind: str, owner_id: str) -> None: ...

    def list_degraded(self) -> List[DegradedOwner]: ...


class DegradedCapabilityRegistry:
    """Default in-process, thread-safe degraded-capability registry.

    Keyed on ``(owner_kind, owner_id)`` so re-marking an already-degraded owner
    updates its record in place rather than duplicating it. Reads return a
    stable, sorted snapshot so operator output is deterministic.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owners: Dict[Tuple[str, str], DegradedOwner] = {}

    def mark(self, owner: DegradedOwner) -> None:
        """Record (or update) a degraded owner. Last write wins per key."""
        with self._lock:
            self._owners[(owner.owner_kind, owner.owner_id)] = owner

    def clear(self, owner_kind: str, owner_id: str) -> None:
        """Remove a degraded owner on recovery. Idempotent."""
        with self._lock:
            self._owners.pop((owner_kind, owner_id), None)

    def list_degraded(self) -> List[DegradedOwner]:
        """Return every currently-degraded owner as a stable, sorted list."""
        with self._lock:
            values = list(self._owners.values())
        return sorted(values, key=lambda o: (o.owner_kind, o.owner_id))

    def to_list(self) -> List[Dict[str, str]]:
        """Convenience: ``list_degraded()`` rendered as plain dicts for JSON."""
        return [owner.to_dict() for owner in self.list_degraded()]
