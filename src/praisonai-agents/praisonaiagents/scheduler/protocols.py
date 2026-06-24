"""
Schedule Store Protocol for PraisonAI Agents.

Defines the interface for schedule persistence backends.
Any object implementing these methods can be used as a schedule store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Protocol, runtime_checkable


@dataclass
class GateResult:
    """Decision returned by a job's pre-run condition gate.

    Attributes:
        run: ``True`` to proceed with the (expensive) model turn,
             ``False`` to skip this tick — no tokens spent, no delivery.
        context: Optional text produced by the gate. When present and
                 ``run`` is ``True``, it is appended to the job message so
                 the same cheap check both *gates* the run and *seeds* it
                 with context (e.g. the new emails the agent should summarise).
        reason: Optional human-readable note recorded with the run
                (e.g. ``"pre-run gate: nothing to do"``).
    """

    run: bool = True
    context: Optional[str] = None
    reason: Optional[str] = None


@runtime_checkable
class JobConditionProtocol(Protocol):
    """Protocol for a cheap, deterministic pre-run gate on a scheduled job.

    A gate decides *whether* a job's model turn should happen at all — a
    cost/efficiency concern, complementary to (and distinct from) the
    wrapper's ``RunPolicy``, which is a *safety* gate on *what* a run may do.

    Implementations live in the wrapper (e.g. a shell-command gate) or in a
    deployment (a Python callable, an MCP/tool probe). The core only owns this
    contract so every front-end (Python ``ScheduleJob``, YAML loader,
    agent-callable schedule tools) shares one shape.
    """

    def should_run(self, job: Any) -> "GateResult":
        """Return a :class:`GateResult` deciding whether ``job`` should run."""
        ...


@runtime_checkable
class ScheduleStoreProtocol(Protocol):
    """Protocol for schedule persistence backends.

    Implementations:
        - ``ConfigYamlScheduleStore`` — YAML config (``~/.praisonai/config.yaml``) [default]
        - ``FileScheduleStore`` — JSON file (``~/.praisonai/schedules/jobs.json``) [legacy]
        - ``_InMemoryScheduleStore`` (in PraisonAIUI) — YAML config.yaml

    Any store that implements these methods can be passed to
    ``ScheduleRunner`` and ``ScheduleLoop``.
    """

    def add(self, job: Any) -> None:
        """Add a job. Raises ``ValueError`` if id already exists."""
        ...

    def get(self, job_id: str) -> Optional[Any]:
        """Get a job by its unique ID."""
        ...

    def list(self, agent_id: Optional[str] = None) -> List[Any]:
        """List all jobs, optionally filtered by agent_id."""
        ...

    def update(self, job: Any) -> None:
        """Update an existing job."""
        ...

    def remove(self, job_id: str) -> bool:
        """Remove a job by ID. Returns True if found and removed."""
        ...

    def get_by_name(self, name: str) -> Optional[Any]:
        """Get a job by its human-readable name."""
        ...

    def remove_by_name(self, name: str) -> bool:
        """Remove a job by name. Returns True if found and removed."""
        ...

    # ── Execution History (optional) ─────────────────────────────────

    def log_run(
        self,
        job_id: str,
        status: str,
        result: Optional[str] = None,
        error: Optional[str] = None,
        duration: float = 0.0,
        delivered: bool = False,
        job_name: str = "",
    ) -> None:
        """Log an execution run for a job.

        Args:
            job_id: ID of the executed job.
            status: Execution status (``"succeeded"``, ``"failed"``, ``"skipped"``).
            result: Agent response text (may be truncated).
            error: Error message if status is ``"failed"``.
            duration: Wall-clock seconds for execution.
            delivered: Whether result was delivered to a channel bot.
            job_name: Human-readable job name for display.

        Note:
            This method is optional. Stores that don't support history
            may implement it as a no-op. Callers should use ``hasattr()``
            to check for support before calling.
        """
        ...

    def get_history(
        self,
        job_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Any]:
        """Get execution history records.

        Args:
            job_id: Optional filter by job ID.
            limit: Maximum number of records to return (default 200).

        Returns:
            List of ``RunRecord`` instances, newest first.

        Note:
            This method is optional. Stores that don't support history
            may return an empty list. Callers should use ``hasattr()``
            to check for support before calling.
        """
        ...
