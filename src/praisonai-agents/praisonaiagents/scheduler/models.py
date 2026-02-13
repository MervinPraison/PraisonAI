"""
Schedule models for PraisonAI Agents.

Lightweight dataclasses — no heavy dependencies.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


@dataclass
class Schedule:
    """When to run a scheduled job.

    Supports three kinds:
    - ``every``: recurring interval in seconds
    - ``cron``: 5-field cron expression (requires optional ``croniter``)
    - ``at``: one-shot ISO 8601 timestamp
    """

    kind: Literal["every", "cron", "at"] = "every"
    every_seconds: Optional[int] = None
    cron_expr: Optional[str] = None
    at: Optional[str] = None
    tz: Optional[str] = None

    # ── serialisation ────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"kind": self.kind}
        if self.every_seconds is not None:
            d["every_seconds"] = self.every_seconds
        if self.cron_expr is not None:
            d["cron_expr"] = self.cron_expr
        if self.at is not None:
            d["at"] = self.at
        if self.tz is not None:
            d["tz"] = self.tz
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Schedule":
        return cls(
            kind=d.get("kind", "every"),
            every_seconds=d.get("every_seconds"),
            cron_expr=d.get("cron_expr"),
            at=d.get("at"),
            tz=d.get("tz"),
        )


@dataclass
class ScheduleJob:
    """A persisted scheduled job.

    Attributes:
        id: Unique identifier (auto-generated).
        name: Human-readable name.
        schedule: When to run.
        message: Prompt / payload to deliver when triggered.
        agent_id: Optional owning agent.
        session_target: ``"main"`` injects into running session;
                        ``"isolated"`` creates a fresh agent turn.
        enabled: Toggle without deleting.
        delete_after_run: Auto-remove after first execution (one-shot).
        created_at: Epoch timestamp.
        last_run_at: Epoch timestamp of most recent execution.
    """

    name: str = ""
    schedule: Schedule = field(default_factory=Schedule)
    message: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_id: Optional[str] = None
    session_target: Literal["main", "isolated"] = "isolated"
    enabled: bool = True
    delete_after_run: bool = False
    created_at: float = field(default_factory=time.time)
    last_run_at: Optional[float] = None

    # ── serialisation ────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "schedule": self.schedule.to_dict(),
            "message": self.message,
            "agent_id": self.agent_id,
            "session_target": self.session_target,
            "enabled": self.enabled,
            "delete_after_run": self.delete_after_run,
            "created_at": self.created_at,
            "last_run_at": self.last_run_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScheduleJob":
        sched_data = d.get("schedule", {})
        return cls(
            id=d.get("id", uuid.uuid4().hex[:12]),
            name=d.get("name", ""),
            schedule=Schedule.from_dict(sched_data) if isinstance(sched_data, dict) else Schedule(),
            message=d.get("message", ""),
            agent_id=d.get("agent_id"),
            session_target=d.get("session_target", "isolated"),
            enabled=d.get("enabled", True),
            delete_after_run=d.get("delete_after_run", False),
            created_at=d.get("created_at", time.time()),
            last_run_at=d.get("last_run_at"),
        )
