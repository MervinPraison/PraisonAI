"""
ScheduledAgentExecutor — bridges ScheduleRunner + agent resolution.

This is a thin reusable bridge that any consumer (UI, CLI, custom app)
can use to poll the scheduler and dispatch due jobs to agents, without
reimplementing the same polling + agent-lookup logic each time.

Lives in the **bot** layer because the gateway polls due jobs and dispatches
to registered agents. Optional :class:`RunPolicy` (wrapper safety gate) is
supported when co-installed via ``praisonai.scheduler.run_policy``.

Usage::

    from praisonaiagents.scheduler import ScheduleRunner, FileScheduleStore
    from praisonai_bot.scheduler.executor import ScheduledAgentExecutor

    store = FileScheduleStore()
    runner = ScheduleRunner(store)

    executor = ScheduledAgentExecutor(
        runner=runner,
        agent_resolver=lambda agent_id: my_gateway.get_agent(agent_id),
    )

    # In your async event loop:
    async for job_result in executor.tick():
        print(f"Job {job_result.job.name}: {job_result.result}")
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import socket
import time
import uuid
from dataclasses import dataclass
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from praisonaiagents.scheduler import ScheduleRunner, ScheduleJob
    from praisonaiagents.scheduler.protocols import JobConditionProtocol

    RunPolicy = Any  # optional wrapper ``praisonai.scheduler.run_policy.RunPolicy``

logger = logging.getLogger(__name__)


@dataclass
class JobResult:
    """Result of a single scheduled job execution.

    Attributes:
        job: The ScheduleJob that was executed.
        result: Agent response (str) or None on failure.
        status: ``"succeeded"``, ``"failed"``, or ``"skipped"``.
        error: Error message if status is ``"failed"``.
        duration: Wall-clock seconds for agent execution.
        delivered: Whether the result was delivered to a channel bot.
        delivery_error: Delivery failure message, separate from execution
            ``error`` so a job that ran but failed to deliver is auditable.
        audit_path: Local path where full output was persisted (if any).
    """

    job: Any  # ScheduleJob
    result: Optional[str] = None
    status: str = "succeeded"
    error: Optional[str] = None
    duration: float = 0.0
    delivered: bool = False
    delivery_error: Optional[str] = None
    audit_path: Optional[str] = None


class ScheduledAgentExecutor:
    """Bridges ScheduleRunner + agent resolution for any consumer.

    This is a **stateless** helper — it does not own a loop or thread.
    Callers decide how and when to call :meth:`tick` or :meth:`run_loop`.

    Parameters:
        runner: An SDK ``ScheduleRunner`` instance.
        agent_resolver: A callable ``(agent_id: str | None) -> Agent``
            that returns an agent for the given ID.  May return ``None``
            if no agent is available.
        delivery_handler: Optional async callable
            ``(delivery: DeliveryTarget, text: str) -> None``.
            Called after successful execution when the job has a
            delivery target.  Typically routes to a channel bot's
            ``send_message()``.
        on_success: Optional callback ``(job, result) -> None``.
        on_failure: Optional callback ``(job, error) -> None``.
        run_policy: Optional :class:`~praisonai.scheduler.run_policy.RunPolicy`
            applied to every unattended run — scopes the agent's toolset,
            scans the assembled prompt, persists a durable output audit, and
            (when configured) delivers a failure summary on failure.
        condition_resolver: Optional callable ``(job) -> JobConditionProtocol``
            returning a *pre-run gate* for the job, or ``None`` for no gate.
            The gate is evaluated **before** the model turn: when it returns
            ``run=False`` the tick is recorded as ``skipped`` (no tokens spent,
            no delivery); when it returns ``run=True`` with ``context`` the
            context is appended to the job message. Defaults to a resolver that
            returns a :class:`~praisonai.scheduler.condition_gate.ShellConditionGate`
            for jobs with a ``pre_run`` command. Pass ``condition_resolver=False``
            (or a resolver returning ``None``) to disable gating entirely.
            This is a *cost/efficiency* gate, complementary to the *safety*
            ``run_policy``.
    """

    def __init__(
        self,
        runner: "ScheduleRunner",
        agent_resolver: Callable[[Optional[str]], Any],
        *,
        delivery_handler: Optional[Callable[..., Any]] = None,
        on_success: Optional[Callable[..., None]] = None,
        on_failure: Optional[Callable[..., None]] = None,
        run_policy: Optional["RunPolicy"] = None,
        condition_resolver: Any = None,
        owner_id: Optional[str] = None,
        lease_seconds: float = 300.0,
    ) -> None:
        self._runner = runner
        self._resolve = agent_resolver
        self._deliver = delivery_handler
        self._on_success = on_success
        self._on_failure = on_failure
        self._run_policy = run_policy
        # ``None`` → use the default shell gate resolver; ``False`` → disable
        # gating; otherwise a user-supplied ``(job) -> gate | None`` callable.
        self._condition_resolver = condition_resolver
        # Stable-per-process identity for atomic job claims so a due job fires
        # at most once across tickers/processes/hosts when the store supports
        # ``claim_due``. Defaults to host+pid+uuid.
        self._owner_id = owner_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._lease_seconds = lease_seconds

    # ── public API ───────────────────────────────────────────────────

    async def tick(self) -> AsyncIterator[JobResult]:
        """Check for due jobs and execute them, yielding results.

        Each due job is dispatched to the resolved agent via
        ``agent.chat(job.message)`` in a background thread (so sync
        agents work correctly in an async context).

        Yields:
            :class:`JobResult` for each due job.

        When the backing store supports an atomic claim (``claim_due``), each
        due job is reserved under a cross-process lock before running so it
        fires **at most once** across all tickers/processes/hosts. Stores
        without that support fall back to the non-atomic ``get_due_jobs`` path.
        """
        claim = getattr(self._runner, "claim_due_jobs", None)
        if callable(claim):
            due_jobs: List["ScheduleJob"] = claim(self._owner_id, self._lease_seconds)
            atomic = getattr(self._runner, "supports_atomic_claim", None)
            atomic_claim = bool(atomic()) if callable(atomic) else False
        else:  # pragma: no cover - older runner without claim support
            due_jobs = self._runner.get_due_jobs()
            atomic_claim = False

        for job in due_jobs:
            try:
                result = await self._execute_one(job)
            finally:
                if atomic_claim:
                    # Release the lease so it does not linger until expiry.
                    try:
                        self._runner.complete_run(job.id, self._owner_id)
                    except Exception as e:  # pragma: no cover - defensive
                        logger.warning(
                            "Failed to release lease for job '%s': %s", job.id, e,
                        )
            yield result

    async def tick_all(self) -> List[JobResult]:
        """Like :meth:`tick` but collects all results into a list."""
        results: List[JobResult] = []
        async for r in self.tick():
            results.append(r)
        return results

    async def run_loop(
        self,
        interval: float = 15.0,
        *,
        max_ticks: Optional[int] = None,
    ) -> None:
        """Convenience loop that calls :meth:`tick` at a fixed interval.

        Args:
            interval: Seconds between ticks (default 15).
            max_ticks: Stop after this many ticks (``None`` = forever).
        """
        tick_count = 0
        logger.info(
            "ScheduledAgentExecutor loop started (interval=%.1fs)", interval,
        )
        try:
            while max_ticks is None or tick_count < max_ticks:
                async for result in self.tick():
                    logger.info(
                        "Job '%s' %s (%.1fs)",
                        getattr(result.job, "name", result.job),
                        result.status,
                        result.duration,
                    )
                tick_count += 1
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("ScheduledAgentExecutor loop stopped after %d ticks", tick_count)

    # ── internals ────────────────────────────────────────────────────

    async def _execute_one(self, job: "ScheduleJob") -> JobResult:
        """Execute a single job and return the result."""
        started = time.time()
        message = str(getattr(job, "message", "") or "")
        agent_id = getattr(job, "agent_id", None)

        # Skip jobs with no message
        if not message:
            duration = time.time() - started
            self._runner.mark_run(
                job,
                status="skipped",
                error="No message configured",
                duration=duration,
            )
            return JobResult(
                job=job,
                status="skipped",
                error="No message configured",
                duration=duration,
            )

        # Resolve the agent
        try:
            agent = self._resolve(agent_id)
        except Exception as e:
            logger.warning("Agent resolution failed for job '%s': %s", job.id, e)
            err = f"Agent resolution failed: {e}"
            duration = time.time() - started
            self._runner.mark_run(job, status="failed", error=err, duration=duration)
            if self._on_failure:
                self._on_failure(job, err)
            return JobResult(
                job=job, status="failed", error=err, duration=duration,
            )

        if agent is None:
            err = f"No agent found for agent_id={agent_id!r}"
            logger.warning("Skipping job '%s': %s", job.id, err)
            duration = time.time() - started
            self._runner.mark_run(job, status="failed", error=err, duration=duration)
            if self._on_failure:
                self._on_failure(job, err)
            return JobResult(
                job=job, status="failed", error=err, duration=duration,
            )

        # Pre-run condition gate (cost/efficiency): a cheap, deterministic
        # check that decides whether the (expensive) model turn is warranted.
        # When it reports "nothing to do" the tick is recorded as ``skipped`` —
        # no tokens spent, no empty message delivered.  When it reports "go"
        # any context it produced is appended to the message before the turn.
        gate = self._resolve_condition(job)
        if gate is not None:
            try:
                # Run off the event loop: the default gate shells out via
                # subprocess.run(), which would otherwise block every other
                # tick / delivery / health-check coroutine for the gate's
                # timeout. Mirrors the agent.chat() offload below.
                decision = await asyncio.to_thread(gate.should_run, job)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(
                    "Pre-run gate raised for job '%s': %s; running anyway",
                    job.id, e,
                )
                decision = None
            if decision is not None and not getattr(decision, "run", True):
                reason = getattr(decision, "reason", None) or "pre-run gate: nothing to do"
                logger.info("Job '%s' skipped by pre-run gate: %s", job.id, reason)
                duration = time.time() - started
                self._runner.mark_run(
                    job, status="skipped", error=reason, duration=duration,
                )
                return JobResult(
                    job=job, status="skipped", error=reason, duration=duration,
                )
            if decision is not None:
                context = getattr(decision, "context", None)
                if context:
                    message = f"{message}\n\n{context}"

        # Run-scoped policy: scan the *untrusted* portion of the run before it
        # reaches the model — the user message plus any runtime-loaded skill or
        # recipe content, which is where injected text actually arrives.  The
        # agent's own admin-authored system prompt / instructions / backstory
        # are trusted configuration and are deliberately NOT fed to the built-in
        # heuristic scanner (it would false-positive on common defensive phrases
        # like "do not reveal your system prompt").  A deployment that wants to
        # scan the full context can supply its own ``scanner``.
        if self._run_policy is not None:
            scan_target = self._assemble_scan_target(agent, message)
            scan = self._run_policy.scan_prompt(scan_target)
            if not scan.ok:
                err = f"Blocked by run policy: {scan.reason}"
                logger.warning(
                    "Job '%s' blocked by run policy: %s", job.id, scan.reason,
                )
                duration = time.time() - started
                self._runner.mark_run(
                    job, status="failed", error=err, duration=duration,
                )
                if self._on_failure:
                    self._on_failure(job, err)
                result = JobResult(
                    job=job, status="failed", error=err, duration=duration,
                )
                await asyncio.to_thread(self._audit_output, job, result)
                await self._maybe_deliver_failure(job, result)
                return result

        # Execute via agent.chat() in a thread (sync-safe)
        # Wire session_target: "main" preserves context, "isolated" is fresh
        # Toolset scoping: restrict the agent's tools for the duration of this
        # unattended run, restoring them afterwards so the policy never leaks
        # into other (attended) uses of the same agent instance.
        _restore_tools = self._apply_toolset_scope(agent)
        try:
            session_target = getattr(job, "session_target", "isolated")
            delivery = getattr(job, "delivery", None)
            session_id = (
                getattr(delivery, "session_id", None)
                if delivery else None
            )

            # Build chat kwargs — only pass session_id if the agent
            # actually accepts it (Core SDK's Agent.chat signature does
            # not currently expose session_id; older assumption caused a
            # TypeError on every scheduled job).
            chat_kwargs: Dict[str, Any] = {}
            try:
                chat_params = inspect.signature(agent.chat).parameters
            except (TypeError, ValueError):  # C-callable or builtin
                chat_params = {}
            supports_session_id = (
                "session_id" in chat_params
                or any(p.kind == inspect.Parameter.VAR_KEYWORD
                       for p in chat_params.values())
            )
            if supports_session_id:
                if session_target == "main" and session_id:
                    chat_kwargs["session_id"] = session_id
                else:
                    chat_kwargs["session_id"] = f"cron_{job.id}"

            result = await asyncio.to_thread(
                agent.chat, message, **chat_kwargs,
            )
            result_str = str(result)
        except Exception as e:
            logger.warning("Job '%s' execution failed: %s", job.id, e)
            err = str(e)
            duration = time.time() - started
            self._runner.mark_run(job, status="failed", error=err, duration=duration)
            if self._on_failure:
                self._on_failure(job, err)
            failed = JobResult(
                job=job, status="failed", error=err, duration=duration,
            )
            await asyncio.to_thread(self._audit_output, job, failed)
            await self._maybe_deliver_failure(job, failed)
            return failed
        finally:
            if _restore_tools is not None:
                _restore_tools()

        # Success - calculate duration before delivery
        duration = time.time() - started

        # Build the success result up-front so the durable output audit is
        # written regardless of whether delivery later succeeds or fails.
        job_result = JobResult(
            job=job,
            result=result_str,
            status="succeeded",
            duration=duration,
        )
        await asyncio.to_thread(self._audit_output, job, job_result)

        # Deliver to channel bot if delivery target exists
        delivered = False
        delivery_error: Optional[str] = None
        delivery = getattr(job, "delivery", None)
        if delivery and self._deliver:
            try:
                coro = self._deliver(delivery, result_str)
                if inspect.isawaitable(coro):
                    await coro
                delivered = True
                logger.info(
                    "Delivered job '%s' result to %s:%s",
                    job.id, delivery.channel, delivery.channel_id,
                )
            except Exception as e:
                delivery_error = str(e)
                logger.warning(
                    "Delivery failed for job '%s' to %s:%s: %s",
                    job.id, delivery.channel, delivery.channel_id, e,
                )

        # Log history with execution results.  last_status is the *execution*
        # status (succeeded) recorded separately from any delivery error, so a
        # job that ran but failed to deliver is auditable.
        self._runner.mark_run(
            job,
            status="succeeded",
            result=result_str,
            duration=duration,
            delivered=delivered,
        )

        if self._on_success:
            self._on_success(job, result_str)

        job_result.delivered = delivered
        job_result.delivery_error = delivery_error
        return job_result

    # ── condition-gate helpers ───────────────────────────────────────

    def _resolve_condition(self, job: "ScheduleJob") -> Optional["JobConditionProtocol"]:
        """Resolve the pre-run gate for ``job`` (or ``None`` for no gate).

        Resolution order:
        - ``condition_resolver is False`` → gating disabled, return ``None``.
        - a user-supplied callable → call it with the job and return its result.
        - default (``None``) → return a :class:`ShellConditionGate` when the
          job declares a ``pre_run`` command, else ``None``.
        """
        resolver = self._condition_resolver
        if resolver is False:
            return None
        if resolver is not None:
            try:
                return resolver(job)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(
                    "condition_resolver raised for job '%s': %s; no gate applied",
                    getattr(job, "id", "?"), e,
                )
                return None
        # Default resolver: only build a gate when there is something to gate on.
        if not (getattr(job, "pre_run", None) or "").strip():
            return None
        from .condition_gate import ShellConditionGate
        return ShellConditionGate()

    # ── run-policy helpers ───────────────────────────────────────────

    def _assemble_scan_target(self, agent: Any, message: str) -> str:
        """Build the *untrusted* content to scan for injection.

        Combines the user message with any runtime-loaded skill or recipe
        content — the surfaces through which attacker-controlled text actually
        reaches an unattended run.  The agent's admin-authored ``system_prompt``
        / ``instructions`` / ``backstory`` are trusted configuration set at
        agent-construction time and are intentionally excluded: feeding them to
        the heuristic scanner caused false positives on common defensive
        instructions (e.g. "do not reveal your system prompt"), which would
        silently block every scheduled run for affected agents.
        """
        parts: List[str] = []
        # Loaded skill/recipe content, if the agent exposes it — this is loaded
        # at run construction and can carry injected text.
        for attr in ("loaded_skills", "skills", "recipes"):
            value = getattr(agent, attr, None)
            if isinstance(value, (list, tuple)):
                for item in value:
                    parts.append(str(item))
            elif isinstance(value, str) and value.strip():
                parts.append(value)
        parts.append(message)
        return "\n".join(parts)

    def _apply_toolset_scope(self, agent: Any) -> Optional[Callable[[], None]]:
        """Scope the agent's tools per the run policy for one run.

        Returns a callable that restores the agent's original tools, or
        ``None`` when no scoping was applied.  Restoration ensures the policy
        does not leak into other (attended) uses of the same agent instance.
        """
        if self._run_policy is None:
            return None
        original = getattr(agent, "tools", None)
        if not original:
            return None
        filtered = self._run_policy.filter_tools(list(original))
        if len(filtered) == len(original):
            return None
        try:
            agent.tools = filtered
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("RunPolicy could not scope agent tools: %s", e)
            return None

        def _restore() -> None:
            try:
                agent.tools = original
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(
                    "RunPolicy could not restore agent tools: %s", e,
                )

        return _restore

    def _audit_output(self, job: "ScheduleJob", result: JobResult) -> None:
        """Persist the full run output to a durable audit path.

        Writes regardless of delivery outcome so a run that succeeded but
        failed to deliver is recoverable.  No-op unless the policy configures
        an ``audit_dir``.
        """
        if self._run_policy is None or not self._run_policy.audit_dir:
            return
        audit_dir = self._run_policy.audit_dir
        try:
            os.makedirs(audit_dir, exist_ok=True)
            ts = time.time_ns()
            # Sanitise job.id into a safe basename so path separators / ".."
            # cannot escape audit_dir, and use a nanosecond stamp so two runs
            # of the same job in the same second do not overwrite each other.
            safe_job_id = "".join(
                ch if ch.isalnum() or ch in ("-", "_", ".") else "_"
                for ch in str(getattr(job, "id", "") or "job")
            ) or "job"
            path = os.path.join(audit_dir, f"{safe_job_id}_{ts}.txt")
            body = result.result if result.result is not None else (result.error or "")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    f"job_id={job.id}\n"
                    f"job_name={getattr(job, 'name', '')}\n"
                    f"status={result.status}\n"
                    f"duration={result.duration:.3f}\n"
                    f"timestamp={ts}\n"
                    f"---\n"
                )
                fh.write(body)
            result.audit_path = path
            logger.info("Persisted run audit for job '%s' to %s", job.id, path)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to write run audit for job '%s': %s", job.id, e)

    async def _maybe_deliver_failure(
        self, job: "ScheduleJob", result: JobResult,
    ) -> None:
        """Fail-closed delivery: send a compact failure summary on failure.

        Active only when the run policy sets ``deliver_on_failure`` and the job
        has a delivery target.  Records any delivery error on the result
        separately from the execution ``error``.
        """
        if self._run_policy is None or not self._run_policy.deliver_on_failure:
            return
        delivery = getattr(job, "delivery", None)
        if not delivery or not self._deliver:
            return
        summary = (
            f"⚠️ Scheduled job '{getattr(job, 'name', job.id)}' failed: "
            f"{result.error or 'unknown error'}"
        )
        try:
            coro = self._deliver(delivery, summary)
            if inspect.isawaitable(coro):
                await coro
            logger.info("Delivered failure summary for job '%s'", job.id)
        except Exception as e:
            result.delivery_error = str(e)
            logger.warning(
                "Failure-summary delivery failed for job '%s': %s", job.id, e,
            )
