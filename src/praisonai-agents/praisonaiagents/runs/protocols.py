"""
Durable run-ledger protocols for recoverable background runs.

When a chat message triggers a long-running agent run (multi-step tools, a
multi-agent workflow, or an async job), the run must survive a gateway
restart: its status should be recoverable, orphaned runs reconciled, and the
originating user notified on completion.

This module holds only the *thin* lifecycle contract — a stable
:class:`RunStatus`, a :class:`RunRecord` payload, and a
:class:`RunLedgerProtocol` the gateway/wrapper implements against. The durable
store (SQLite by default) and channel wake-back are heavy integrations that
live behind this protocol; see :mod:`praisonaiagents.runs.sqlite_ledger` for a
zero-dependency default implementation.

Design: no heavy imports, no I/O — pure protocol + data shapes so the store is
pluggable and core stays lightweight.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

__all__ = [
    "RunStatus",
    "RunRecord",
    "RunLedgerProtocol",
    "TerminalOutcomeDelivererProtocol",
    "notify_recovered",
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
]


class RunStatus(str, Enum):
    """Lifecycle status of a durable run.

    ``str`` subclass so values serialise transparently (JSON, SQLite) and
    compare equal to their string form (``RunStatus.RUNNING == "running"``).
    """

    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"
    #: A status this version does not recognise (e.g. written by a newer
    #: process). Deliberately neither active nor terminal so recovery never
    #: finalises — or drops — a run whose real state is unknown here.
    UNKNOWN = "unknown"

    @property
    def is_terminal(self) -> bool:
        """Whether this status ends the run (no further transitions expected)."""
        return self in TERMINAL_STATUSES

    @property
    def is_active(self) -> bool:
        """Whether the run is still in flight (recoverable on restart)."""
        return self in ACTIVE_STATUSES


#: Statuses considered still in flight — candidates for orphan recovery.
ACTIVE_STATUSES = frozenset(
    {RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING}
)

#: Statuses considered done — a terminal outcome has been recorded.
TERMINAL_STATUSES = frozenset(
    {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.LOST,
    }
)


@dataclass
class RunRecord:
    """A durable record of a single background/async run.

    Persisted so the run survives a gateway restart. ``channel``/``thread_id``
    capture the origin route needed to wake the user back on completion.
    """

    run_id: str
    agent_id: str = ""
    channel: str = ""
    thread_id: Optional[str] = None
    status: RunStatus = RunStatus.QUEUED
    progress: Optional[str] = None
    terminal_outcome: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    #: Whether this run's terminal outcome has been delivered back to its
    #: origin ``channel``/``thread_id``. Enables exactly-once wake-back: a run
    #: already ``delivered`` is never re-notified, and a terminal/recovered run
    #: not yet ``delivered`` is a visible, retryable non-outcome rather than a
    #: silent one. ``False`` preserves prior behaviour when no deliverer wires
    #: the seam (see :func:`notify_recovered`).
    delivered: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict (JSON/SQLite friendly)."""
        return {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "channel": self.channel,
            "thread_id": self.thread_id,
            "status": RunStatus(self.status).value,
            "progress": self.progress,
            "terminal_outcome": self.terminal_outcome,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata or {}),
            "delivered": bool(self.delivered),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunRecord":
        """Rehydrate from a plain dict produced by :meth:`to_dict`."""
        status = data.get("status", RunStatus.QUEUED)
        try:
            status = RunStatus(status)
        except ValueError:
            # A status this version doesn't recognise (e.g. written by a newer
            # process). Map to UNKNOWN — neither active nor terminal — so a
            # still-running run is not wrongly finalised as LOST or dropped.
            status = RunStatus.UNKNOWN
        return cls(
            run_id=data["run_id"],
            agent_id=data.get("agent_id", "") or "",
            channel=data.get("channel", "") or "",
            thread_id=data.get("thread_id"),
            status=status,
            progress=data.get("progress"),
            terminal_outcome=data.get("terminal_outcome"),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            metadata=dict(data.get("metadata") or {}),
            delivered=bool(data.get("delivered", False)),
        )


@runtime_checkable
class RunLedgerProtocol(Protocol):
    """Pluggable durable store for :class:`RunRecord` entries.

    Implementations persist runs to a durable backend (SQLite by default) so
    they survive a gateway restart. The gateway calls :meth:`recover_orphans`
    on boot to reconcile runs left in an active state by a crashed process.
    """

    def upsert(self, record: RunRecord) -> None:
        """Insert or update ``record`` (keyed by ``run_id``)."""
        ...

    def get(self, run_id: str) -> Optional[RunRecord]:
        """Return the record for ``run_id`` or ``None`` if unknown."""
        ...

    def list_active(self) -> List[RunRecord]:
        """Return all runs still in an active (in-flight) status."""
        ...

    def recover_orphans(self) -> List[RunRecord]:
        """Reconcile active runs left over from a crashed process.

        Called on gateway boot: marks still-active runs as ``LOST`` (or as the
        implementation defines) and returns the affected records so the
        gateway can wake their origin channels.
        """
        ...

    def mark_delivered(self, run_id: str) -> None:
        """Record that ``run_id``'s terminal outcome reached its origin.

        The exactly-once bookkeeping half of the wake-back guarantee: once a
        terminal/recovered run is delivered, this marks it so a later
        :func:`notify_recovered` (e.g. on the next restart) never re-notifies.
        """
        ...


@runtime_checkable
class TerminalOutcomeDelivererProtocol(Protocol):
    """Transport that wakes a run's origin channel with its terminal outcome.

    Core owns the *guarantee* (a terminal/recovered run is delivered exactly
    once); the wrapper supplies only this concrete transport. Implementations
    send ``record.terminal_outcome`` to ``record.channel``/``record.thread_id``
    and return whether the send landed, so a failure is recorded and retried
    rather than silently dropped.
    """

    async def deliver_terminal(self, record: RunRecord) -> bool:
        """Deliver ``record``'s terminal outcome to its origin channel.

        Returns ``True`` when the outcome reached the origin, ``False`` when it
        could not (so the run stays undelivered and is retried next time).
        """
        ...


async def notify_recovered(
    ledger: "RunLedgerProtocol",
    deliverer: "TerminalOutcomeDelivererProtocol",
) -> int:
    """Guarantee every recovered ``LOST`` run wakes its origin, exactly once.

    Closes the loop the ledger only *documents*: :meth:`recover_orphans`
    reconciles orphaned runs to ``LOST`` and returns them so their origin can
    be told the run did not finish — but nothing in core enforced that the
    telling actually happened. This binder does: for each recovered record it
    invokes ``deliverer.deliver_terminal`` and, only on success, marks the run
    ``delivered`` via :meth:`RunLedgerProtocol.mark_delivered`. A delivery that
    fails is left undelivered (a visible, retryable non-outcome) rather than
    silently skipped.

    Mirrors :meth:`BackgroundJobManager.reconcile_on_start`'s ``redeliver``
    seam. Best-effort per record: a transport that raises is treated as a
    failed (retryable) delivery, never crashing recovery for the other runs.

    Args:
        ledger: The durable ledger to reconcile and record delivery against.
        deliverer: The concrete channel transport (supplied by the wrapper).

    Returns:
        The number of recovered runs successfully delivered this call.
    """
    delivered = 0
    for record in ledger.recover_orphans():
        try:
            ok = await deliverer.deliver_terminal(record)
        except Exception:  # noqa: BLE001 — a transport error is a retryable miss
            ok = False
        if ok:
            ledger.mark_delivered(record.run_id)
            delivered += 1
    return delivered
