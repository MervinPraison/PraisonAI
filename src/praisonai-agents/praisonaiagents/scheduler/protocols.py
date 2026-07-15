"""
Schedule Store Protocol for PraisonAI Agents.

Defines the interface for schedule persistence backends.
Any object implementing these methods can be used as a schedule store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Protocol, runtime_checkable


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
class SchedulerProviderProtocol(Protocol):
    """Protocol for a scheduler *trigger* backend — decides **when** to fire.

    Complements :class:`ScheduleStoreProtocol`: the store owns *where* jobs
    live and *what* is due (via ``claim_due``); a provider owns *when* the
    firing check happens. The provider NEVER decides what fires or how a result
    is delivered — it just calls ``on_due`` whenever a tick should occur, and
    the shared ``ScheduleRunner`` + store then claim and fire due jobs.

    This makes the firing mechanism as pluggable as the store already is:
        - ``InProcessScheduleProvider`` (the built-in ``ScheduleLoop``) — an
          always-on daemon thread polling every ``tick_seconds`` [default].
        - An external provider — a systemd/launchd timer, a cloud scheduler
          POSTing a gateway endpoint, an APScheduler cron trigger, or a
          Kubernetes ``CronJob`` — that fires event-driven / serverless with no
          always-on poll thread. Heavy provider implementations live in the
          wrapper behind optional deps.

    Any object implementing ``start`` + ``stop`` satisfies this contract and can
    drive firing uniformly.
    """

    def start(
        self,
        on_due: Callable[[], None],
        store: Optional["ScheduleStoreProtocol"] = None,
    ) -> None:
        """Begin driving firing.

        Args:
            on_due: Called whenever a tick should occur. The shared runner then
                claims and fires due jobs. A provider MAY call this on a poll
                interval (in-process) or on an inbound external signal
                (event-driven / serverless).
            store: Optional schedule store the provider may inspect. Firing
                logic stays in the runner/store regardless of provider.
        """
        ...

    def stop(self) -> None:
        """Stop driving firing and release any resources (threads, timers)."""
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

    # ── Atomic claim / lease (optional) ──────────────────────────────

    def claim_due(
        self,
        now: float,
        owner_id: str,
        lease_seconds: float = 300.0,
    ) -> List[Any]:
        """Atomically claim all due jobs, returning only those *this* caller won.

        This is the at-most-once primitive: a due job must fire on exactly one
        ticker even when several processes/hosts poll the same store. An
        implementation MUST perform the "is due? -> reserve" step atomically
        under a cross-process lock (e.g. an OS advisory file lock or a DB
        compare-and-set), pre-advancing the job's schedule and/or taking a
        short lease keyed by ``job_id + scheduled_fire_time`` before returning
        it. A competing caller that loses the race receives an empty list for
        that job and skips silently.

        Args:
            now: Epoch seconds treated as the current time.
            owner_id: Stable identifier for the claiming ticker (process/host).
            lease_seconds: How long the claim is held before it may be
                reclaimed. A claim not marked complete (crash) expires after
                this window so the run is not lost forever.

        Returns:
            The list of jobs successfully claimed by ``owner_id``. Jobs claimed
            by another ticker are omitted.

        Note:
            This method is OPTIONAL. Stores that cannot provide cross-process
            atomicity may omit it; callers should use ``hasattr()`` to detect
            support and fall back to a non-atomic "list due -> run" path.
        """
        ...

    def complete(self, job_id: str, owner_id: str) -> None:
        """Release the lease for ``job_id`` held by ``owner_id`` after a run.

        Called once the side effect for a claimed job has finished (success or
        failure) so the lease does not linger until it expires. Idempotent and
        a no-op if the lease is not held by ``owner_id``.

        Note:
            This method is OPTIONAL and pairs with :meth:`claim_due`.
        """
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
