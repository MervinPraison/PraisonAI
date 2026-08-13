"""
Schedule Store Protocol for PraisonAI Agents.

Defines the interface for schedule persistence backends.
Any object implementing these methods can be used as a schedule store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable


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
        no_change: When ``True`` the gate observed a *watched source that has
                 not changed since the last tick* — a distinct "monitor mode"
                 outcome from a generic ``run=False`` skip. The tick is
                 suppressed silently (no tokens, no delivery) and recorded as
                 ``no_change`` rather than ``skipped``, so an operator can tell
                 "a watched source was unchanged" apart from "the gate said
                 don't run". Implies ``run=False``. Backward-compatible: gates
                 that never set it behave exactly as before.
        state_updates: Optional bounded key/value the gate wants persisted for
                 the *next* tick (e.g. the last-seen hash, a cursor / watermark)
                 via a :class:`JobStateStoreProtocol`. ``None`` means "write
                 nothing" — an error probe leaves prior state untouched so a
                 later recovery to the prior output still suppresses. The core
                 owns only the shape; the wrapper decides where to persist it.
    """

    run: bool = True
    context: Optional[str] = None
    reason: Optional[str] = None
    no_change: bool = False
    state_updates: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        # ``no_change`` is a silent-suppress outcome and, per the field's
        # contract, *implies* ``run=False``. Enforce the invariant so a gate
        # that sets only ``no_change=True`` (leaving ``run`` at its default)
        # can never let a runner fire a tick the contract defines as
        # suppressed.
        if self.no_change:
            self.run = False


@runtime_checkable
class JobStateStoreProtocol(Protocol):
    """Protocol for a small, bounded per-job durable scratchpad.

    Gives a scheduled automation *memory* across wake-ups so it can hold
    cursors, watermarks, or a last-seen hash and do incremental work
    ("summarise items new since last run", "alert only on newly failing
    checks"). Keyed by job id; the store is expected to bound the persisted
    size so a runaway write cannot grow unbounded, and to clear a job's state
    when that job is removed.

    Complements :class:`ScheduleStoreProtocol` (which owns *jobs*): this owns a
    job's *state*. The core owns only the contract; a concrete store (JSON
    file, config-yaml section, DB) lives in the wrapper alongside the heavy
    monitor gate that reads and writes it. All methods are OPTIONAL for a
    store to provide — callers should use ``hasattr()`` to detect support and
    treat absence as "no per-job state" (today's stateless behaviour).
    """

    def get_state(self, job_id: str) -> Dict[str, Any]:
        """Return the persisted state dict for ``job_id`` (``{}`` if none)."""
        ...

    def set_state(self, job_id: str, state: Dict[str, Any]) -> None:
        """Persist ``state`` for ``job_id`` (size-capped by the implementation)."""
        ...

    def clear_state(self, job_id: str) -> None:
        """Drop any persisted state for ``job_id`` (called when a job is removed)."""
        ...


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

    A gate may be *stateless* (sees only ``job``) or *stateful*: a stateful
    "monitor" gate accepts the job's prior persisted ``state`` and returns a
    :class:`GateResult` whose ``no_change`` / ``state_updates`` fields let it
    suppress an unchanged source and carry a last-seen hash / watermark to the
    next tick. The ``state`` parameter is optional and keyword-only so existing
    stateless gates (``should_run(self, job)``) satisfy the protocol unchanged
    under ``runtime_checkable`` (which matches on method *name*).

    Caller contract: because a legacy stateless gate accepts only ``job``,
    callers MUST NOT unconditionally pass ``state=``. Detect capability first —
    e.g. call ``should_run(job, state=prior)`` only when the gate opts into
    state, otherwise fall back to ``should_run(job)`` — so stateless gates keep
    working unchanged and never raise ``TypeError``.
    """

    def should_run(
        self, job: Any, *, state: Optional[Dict[str, Any]] = None
    ) -> "GateResult":
        """Return a :class:`GateResult` deciding whether ``job`` should run.

        Args:
            job: The scheduled job under evaluation.
            state: Optional prior per-job state (from a
                :class:`JobStateStoreProtocol`) for a stateful monitor gate to
                compare against. Stateless gates ignore it.
        """
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

    def list(
        self,
        agent_id: Optional[str] = None,
        principal: Optional[str] = None,
    ) -> List[Any]:
        """List all jobs, optionally filtered by agent_id and/or principal.

        ``principal`` is the resolved end-user identity used to isolate one
        gateway user's automations from another's. ``None`` returns
        everything (global / single-tenant behaviour).
        """
        ...

    def update(self, job: Any) -> None:
        """Update an existing job."""
        ...

    def remove(self, job_id: str) -> bool:
        """Remove a job by ID. Returns True if found and removed."""
        ...

    def get_by_name(
        self,
        name: str,
        principal: Optional[str] = None,
    ) -> Optional[Any]:
        """Get a job by its human-readable name.

        ``principal`` scopes the lookup to the resolved end-user identity: a
        job owned by a different principal is treated as not found. ``None``
        returns any match (global / single-tenant behaviour).
        """
        ...

    def remove_by_name(self, name: str, principal: Optional[str] = None) -> bool:
        """Remove a job by name. Returns True if found and removed.

        ``principal`` scopes the removal to the resolved end-user identity so
        one gateway user cannot delete another's automation by name. ``None``
        removes any match (global / single-tenant behaviour).
        """
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
