"""
Schedule Store Protocol for PraisonAI Agents.

Defines the interface for schedule persistence backends.
Any object implementing these methods can be used as a schedule store.
"""

from __future__ import annotations

from typing import Any, List, Optional, Protocol, runtime_checkable


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
