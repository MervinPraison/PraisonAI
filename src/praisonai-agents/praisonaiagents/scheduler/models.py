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
class DeliveryTarget:
    """Where to deliver the result when a scheduled job fires.

    Attributes:
        channel: Platform name (``"telegram"``, ``"discord"``,
                 ``"slack"``, ``"whatsapp"``).
        channel_id: Platform-specific chat / channel / group ID.
        thread_id: Optional thread ID for threaded delivery.
        session_id: Optional session ID to preserve conversation
                    context when the cron fires.
    """

    channel: str = ""
    channel_id: str = ""
    thread_id: Optional[str] = None
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "channel": self.channel,
            "channel_id": self.channel_id,
        }
        if self.thread_id is not None:
            d["thread_id"] = self.thread_id
        if self.session_id is not None:
            d["session_id"] = self.session_id
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DeliveryTarget":
        return cls(
            channel=d.get("channel", ""),
            channel_id=d.get("channel_id", ""),
            thread_id=d.get("thread_id"),
            session_id=d.get("session_id"),
        )


@dataclass
class RunRecord:
    """A single execution record for a scheduled job.

    Attributes:
        job_id: ID of the job that was executed.
        job_name: Human-readable name of the job.
        status: Execution status (``"succeeded"``, ``"failed"``, ``"skipped"``).
        result: Agent response text (truncated if very long).
        error: Error message if status is ``"failed"``.
        duration: Wall-clock seconds for execution.
        delivered: Whether result was delivered to a channel bot.
        timestamp: Epoch timestamp of execution.
    """

    job_id: str
    job_name: str = ""
    status: Literal["succeeded", "failed", "skipped"] = "succeeded"
    result: Optional[str] = None
    error: Optional[str] = None
    duration: float = 0.0
    delivered: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_name": self.job_name,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "duration": self.duration,
            "delivered": self.delivered,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RunRecord":
        return cls(
            job_id=d.get("job_id", ""),
            job_name=d.get("job_name", ""),
            status=d.get("status", "succeeded"),
            result=d.get("result"),
            error=d.get("error"),
            duration=d.get("duration", 0.0),
            delivered=d.get("delivered", False),
            timestamp=d.get("timestamp", time.time()),
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
        delivery: Optional delivery target for routing results back
                  to a channel bot (e.g. Telegram chat).
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
    delivery: Optional[DeliveryTarget] = None

    # ── serialisation ────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
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
        if self.delivery is not None:
            d["delivery"] = self.delivery.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScheduleJob":
        sched_data = d.get("schedule", {})
        delivery_data = d.get("delivery")
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
            delivery=DeliveryTarget.from_dict(delivery_data) if isinstance(delivery_data, dict) else None,
        )
