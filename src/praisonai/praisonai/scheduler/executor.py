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
    """

    job: Any  # ScheduleJob
    result: Optional[str] = None
    status: str = "succeeded"
    error: Optional[str] = None
    duration: float = 0.0
    delivered: bool = False


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
    """

    def __init__(
        self,
        runner: "ScheduleRunner",
        agent_resolver: Callable[[Optional[str]], Any],
        *,
        delivery_handler: Optional[Callable[..., Any]] = None,
        on_success: Optional[Callable[..., None]] = None,
        on_failure: Optional[Callable[..., None]] = None,
    ) -> None:
        self._runner = runner
        self._resolve = agent_resolver
        self._deliver = delivery_handler
        self._on_success = on_success
        self._on_failure = on_failure

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
            self._runner.mark_run(job)
            return JobResult(
                job=job,
                status="skipped",
                error="No message configured",
                duration=time.time() - started,
            )

        # Resolve the agent
        try:
            agent = self._resolve(agent_id)
        except Exception as e:
            logger.warning("Agent resolution failed for job '%s': %s", job.id, e)
            err = f"Agent resolution failed: {e}"
            if self._on_failure:
                self._on_failure(job, err)
            return JobResult(
                job=job, status="failed", error=err, duration=time.time() - started,
            )

        if agent is None:
            err = f"No agent found for agent_id={agent_id!r}"
            logger.warning("Skipping job '%s': %s", job.id, err)
            if self._on_failure:
                self._on_failure(job, err)
            return JobResult(
                job=job, status="failed", error=err, duration=time.time() - started,
            )

        # Execute via agent.chat() in a thread (sync-safe)
        try:
            result = await asyncio.to_thread(agent.chat, message)
            result_str = str(result)
        except Exception as e:
            logger.warning("Job '%s' execution failed: %s", job.id, e)
            err = str(e)
            if self._on_failure:
                self._on_failure(job, err)
            return JobResult(
                job=job, status="failed", error=err, duration=time.time() - started,
            )

        # Success
        self._runner.mark_run(job)
        duration = time.time() - started

        # Deliver to channel bot if delivery target exists
        delivered = False
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
                logger.warning(
                    "Delivery failed for job '%s' to %s:%s: %s",
                    job.id, delivery.channel, delivery.channel_id, e,
                )

        if self._on_success:
            self._on_success(job, result_str)

        return JobResult(
            job=job,
            result=result_str,
            status="succeeded",
            duration=duration,
            delivered=delivered,
        )
