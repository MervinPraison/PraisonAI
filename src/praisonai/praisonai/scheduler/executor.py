"""
ScheduledAgentExecutor — bridges ScheduleRunner + agent resolution.

This is a thin reusable bridge that any consumer (UI, CLI, custom app)
can use to poll the scheduler and dispatch due jobs to agents, without
reimplementing the same polling + agent-lookup logic each time.

Lives in the **wrapper** layer (not the SDK core) because it composes
two independent core modules: gateway (agent registry) and scheduler
(due-job detection).

Usage::

    from praisonaiagents.scheduler import ScheduleRunner, FileScheduleStore
    from praisonai.scheduler.executor import ScheduledAgentExecutor

    store = FileScheduleStore()
    runner = ScheduleRunner(store)

    executor = ScheduledAgentExecutor(
        runner=runner,
        agent_resolver=lambda agent_id: my_gateway.get_agent(agent_id),
    )

    # In your async event loop:
    async for job, result in executor.tick():
        print(f"Job {job.name}: {result}")
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
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
    from .run_policy import RunPolicy

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
    ) -> None:
        self._runner = runner
        self._resolve = agent_resolver
        self._deliver = delivery_handler
        self._on_success = on_success
        self._on_failure = on_failure
        self._run_policy = run_policy

    # ── public API ───────────────────────────────────────────────────

    async def tick(self) -> AsyncIterator[JobResult]:
        """Check for due jobs and execute them, yielding results.

        Each due job is dispatched to the resolved agent via
        ``agent.chat(job.message)`` in a background thread (so sync
        agents work correctly in an async context).

        Yields:
            :class:`JobResult` for each due job.
        """
        due_jobs: List["ScheduleJob"] = self._runner.get_due_jobs()

        for job in due_jobs:
            result = await self._execute_one(job)
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
        message = getattr(job, "message", "") or ""
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

        # Run-scoped policy: scan the assembled prompt before it reaches the
        # model.  The assembled prompt is the user message plus any runtime
        # context (system prompt / loaded skill or recipe content) the agent
        # would prepend — scanning the create-time message alone is not enough.
        if self._run_policy is not None:
            assembled = self._assemble_prompt(agent, message)
            scan = self._run_policy.scan_prompt(assembled)
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
                self._audit_output(job, result)
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
            import inspect as _inspect
            chat_kwargs: Dict[str, Any] = {}
            try:
                chat_params = _inspect.signature(agent.chat).parameters
            except (TypeError, ValueError):  # C-callable or builtin
                chat_params = {}
            supports_session_id = (
                "session_id" in chat_params
                or any(p.kind == _inspect.Parameter.VAR_KEYWORD
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
            self._audit_output(job, failed)
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
        self._audit_output(job, job_result)

        # Deliver to channel bot if delivery target exists
        delivered = False
        delivery_error: Optional[str] = None
        delivery = getattr(job, "delivery", None)
        if delivery and self._deliver:
            try:
                coro = self._deliver(delivery, result_str)
                if asyncio.iscoroutine(coro):
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

    # ── run-policy helpers ───────────────────────────────────────────

    def _assemble_prompt(self, agent: Any, message: str) -> str:
        """Build the *fully assembled* prompt for scanning.

        Combines the user message with any runtime context the agent would
        prepend — its system prompt / instructions and loaded skill or recipe
        content — so the scan covers content injected at run construction, not
        only the create-time message.
        """
        parts: List[str] = []
        for attr in ("system_prompt", "instructions", "backstory"):
            value = getattr(agent, attr, None)
            if isinstance(value, str) and value.strip():
                parts.append(value)
        # Loaded skill/recipe content, if the agent exposes it.
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
            except Exception:  # pragma: no cover - defensive
                pass

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
            ts = int(time.time())
            path = os.path.join(audit_dir, f"{job.id}_{ts}.txt")
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
            if asyncio.iscoroutine(coro):
                await coro
            logger.info("Delivered failure summary for job '%s'", job.id)
        except Exception as e:
            result.delivery_error = str(e)
            logger.warning(
                "Failure-summary delivery failed for job '%s': %s", job.id, e,
            )
