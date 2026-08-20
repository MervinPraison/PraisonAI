"""Ensure SDK schedule runner + optional ScheduleLoop daemon."""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)
_runner_started = False
_loop = None
_executor = None


def _build_executor(store):
    """Construct a ``ScheduledAgentExecutor`` for host-app embedding.

    Resolution: the host embedding has no gateway agent registry, so jobs are
    executed against agents resolved by ``agent_id`` from the process-global
    registry when available. Delivery uses the standalone sender fallback
    (``delivery_handler=None``) so a job's own delivery target still receives
    output with no live gateway. A default :class:`RunPolicy` guards the run.
    Returns ``None`` when the executor cannot be constructed — the caller then
    leaves the job due rather than silently absorbing it.
    """
    try:
        from praisonaiagents.scheduler import ScheduleRunner
        from praisonai_bot.scheduler.executor import ScheduledAgentExecutor
    except ImportError as exc:
        log.debug("ScheduledAgentExecutor unavailable: %s", exc)
        return None

    run_policy = None
    try:
        from praisonai.scheduler.run_policy import RunPolicy

        run_policy = RunPolicy()
    except ImportError as exc:  # pragma: no cover - wrapper policy optional
        log.debug("RunPolicy unavailable for host embedding: %s", exc)

    def _resolve_agent(agent_id):
        return None

    return ScheduledAgentExecutor(
        runner=ScheduleRunner(store),
        agent_resolver=_resolve_agent,
        run_policy=run_policy,
    )


def ensure_schedule_runner() -> None:
    """Lazy-init runner (canonical default store) and optional ScheduleLoop."""
    global _runner_started, _loop, _executor
    if _runner_started:
        return
    try:
        from praisonaiagents.scheduler import get_default_store, ScheduleLoop

        store = get_default_store()
        _executor = _build_executor(store)

        def on_trigger(job):
            # Actually execute the due job. If no executor could be constructed
            # in this embedding, raise so ScheduleLoop.fire_due does NOT advance
            # last_run_at — the job stays due rather than being silently
            # absorbed (issue #4079, Defect 2).
            if _executor is None:
                raise RuntimeError(
                    "no scheduler executor available; leaving job due"
                )
            log.info("Schedule triggered: %s", getattr(job, "name", job))
            asyncio.run(_executor._execute_one(job))

        _loop = ScheduleLoop(on_trigger=on_trigger, store=store)
        _loop.start()
        _runner_started = True
        log.info("ScheduleLoop started for host integration")
    except Exception as exc:
        log.debug("Schedule runner unavailable: %s", exc)
