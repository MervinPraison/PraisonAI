"""
Schedule Store Protocol for PraisonAI Agents.

Defines the interface for schedule persistence backends.
Any object implementing these methods can be used as a schedule store.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .models import ScheduleJob


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
