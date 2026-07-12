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
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunRecord":
        """Rehydrate from a plain dict produced by :meth:`to_dict`."""
        status = data.get("status", RunStatus.QUEUED)
        try:
            status = RunStatus(status)
        except ValueError:
            status = RunStatus.LOST
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
