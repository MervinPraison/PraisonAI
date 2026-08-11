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
from typing import Dict, List, Optional, Protocol, Tuple, runtime_checkable

# Closed vocabularies kept as module constants so owners and readers agree on
# the shape without importing an enum-heavy dependency.
OWNER_KINDS: Tuple[str, ...] = ("channel", "provider", "capability", "route", "gateway")
DEGRADED_STATES: Tuple[str, ...] = ("cold", "stale")


class OwnerUnavailable(Exception):
    """Typed, redacted outcome raised when work targets a degraded owner.

    Issue #3640: the fail-closed read of the degraded-owner contract. When a
    request targets an owner already recorded as degraded, the dispatch path
    calls :meth:`DegradedCapabilityRegistry.assert_owner_available` (or the
    module-level :func:`assert_owner_available`) and this is raised instead of
    letting the work proceed and fail silently. It carries only the redacted,
    operator-safe fields already on :class:`DegradedOwner` — never token/secret
    material — so the loop can turn it into a visible "unavailable, here is the
    next action" outcome.
    """

    def __init__(self, owner: "DegradedOwner") -> None:
        self.owner = owner
        self.owner_kind = owner.owner_kind
        self.owner_id = owner.owner_id
        self.state = owner.state
        self.reason = owner.reason
        self.retry_hint = owner.retry_hint
        super().__init__(
            f"{owner.owner_kind} {owner.owner_id!r} unavailable ({owner.state}): "
            f"{owner.reason}"
            + (f" — {owner.retry_hint}" if owner.retry_hint else "")
        )

    def to_dict(self) -> Dict[str, str]:
        """Render the redacted outcome for a JSON/operator surface."""
        return self.owner.to_dict()


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

    Note (Issue #3640): the fail-closed point read ``find`` is deliberately
    *not* on this base contract. Adding it here would break structural
    ``isinstance`` conformance for any existing external registry that only
    implemented ``mark``/``clear``/``list_degraded``. The point read lives on
    the extended :class:`DegradedCapabilityLookupProtocol`, and the module
    guard degrades gracefully to ``list_degraded()`` when ``find`` is absent.
    """

    def mark(self, owner: DegradedOwner) -> None: ...

    def clear(self, owner_kind: str, owner_id: str) -> None: ...

    def list_degraded(self) -> List[DegradedOwner]: ...


@runtime_checkable
class DegradedCapabilityLookupProtocol(DegradedCapabilityProtocol, Protocol):
    """Extended contract for registries that support the point read (Issue #3640).

    Kept separate from :class:`DegradedCapabilityProtocol` so upgrading does not
    silently break structural conformance for pre-existing external registries.
    """

    def find(self, owner_kind: str, owner_id: str) -> Optional[DegradedOwner]: ...


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

    def find(self, owner_kind: str, owner_id: str) -> Optional[DegradedOwner]:
        """Return the degraded record for one owner, or ``None`` if healthy.

        Issue #3640: the point read the fail-closed dispatch path uses to ask
        "is *this* owner currently degraded?" without scanning the whole list.
        """
        with self._lock:
            return self._owners.get((owner_kind, owner_id))

    def assert_owner_available(self, owner_kind: str, owner_id: str) -> None:
        """Fail-closed guard: raise :class:`OwnerUnavailable` if degraded.

        Issue #3640: the read that turns a recorded degradation into a fact the
        request path consults. A dispatch path calls this before doing work for
        an owner; if that owner is degraded the request short-circuits to a
        typed, redacted "unavailable — next action" outcome instead of
        proceeding and failing silently. No-op when the owner is healthy.
        """
        owner = self.find(owner_kind, owner_id)
        if owner is not None:
            raise OwnerUnavailable(owner)

    def to_list(self) -> List[Dict[str, str]]:
        """Convenience: ``list_degraded()`` rendered as plain dicts for JSON."""
        return [owner.to_dict() for owner in self.list_degraded()]


def assert_owner_available(
    registry: Optional[DegradedCapabilityProtocol],
    owner_kind: str,
    owner_id: str,
) -> None:
    """Fail-closed guard for a possibly-absent registry (Issue #3640).

    The dispatch path holds an *optional* shared registry (a gateway may run
    without one). This wrapper is a no-op when ``registry`` is ``None`` and
    otherwise delegates to :meth:`DegradedCapabilityRegistry.assert_owner_available`,
    raising :class:`OwnerUnavailable` if the owner is degraded — so a caller can
    guard a request without repeating the ``None`` check at every call site.
    """
    if registry is None:
        return
    guard = getattr(registry, "assert_owner_available", None)
    if callable(guard):
        guard(owner_kind, owner_id)
        return
    # Backward compatibility (Issue #3640): a pre-existing registry may implement
    # only ``mark``/``clear``/``list_degraded`` and have neither the new guard nor
    # ``find``. Prefer the point read when present, otherwise derive the owner
    # from ``list_degraded()`` so a legacy registry still fails-closed rather than
    # raising ``AttributeError``.
    find = getattr(registry, "find", None)
    if callable(find):
        owner = find(owner_kind, owner_id)
    else:
        owner = next(
            (
                o
                for o in registry.list_degraded()
                if o.owner_kind == owner_kind and o.owner_id == owner_id
            ),
            None,
        )
    if owner is not None:
        raise OwnerUnavailable(owner)
