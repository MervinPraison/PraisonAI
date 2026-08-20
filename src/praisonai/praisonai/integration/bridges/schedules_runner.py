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

    The host embedding has no gateway agent registry, so ``agent_id`` cannot be
    resolved to a live agent here — message jobs are surfaced by the executor as
    a recorded ``failed`` run with a clear reason rather than crashing the tick,
    while ``command`` jobs (which take no model turn) execute normally. Delivery
    uses the standalone sender fallback (``delivery_handler=None``) so a job's
    own delivery target still receives output with no live gateway. A default
    :class:`RunPolicy` guards the run.

    Returns ``None`` when the executor cannot be constructed — the caller then
    does **not** start the poll loop, so due jobs are left genuinely due (never
    claimed/consumed) until an executor is available.
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
        # No process-global agent registry exists in the host embedding; a
        # message job's ``agent_id`` therefore resolves to nothing here. The
        # executor records this as a ``failed`` run (auditable) instead of
        # silently dropping it; ``command`` jobs never reach this resolver.
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

        # Only poll when we can actually execute. The canonical store claims a
        # due job *atomically* — advancing ``last_run_at`` and deleting one-shot
        # jobs at claim time (before the trigger runs). If we started the loop
        # with no executor and let ``on_trigger`` raise, ``fire_due`` would still
        # have consumed the occurrence (the claim persisted the advance), losing
        # one-shot and long-interval work. So when no executor can be built we
        # leave the loop unstarted — nothing is claimed, every job stays truly
        # due until a later start finds an executor (issue #4079, Defect 2).
        if _executor is None:
            log.debug(
                "Schedule executor unavailable; poll loop not started "
                "(jobs left due, none claimed)"
            )
            return

        def on_trigger(job):
            log.info("Schedule triggered: %s", getattr(job, "name", job))
            asyncio.run(_executor._execute_one(job))

        _loop = ScheduleLoop(on_trigger=on_trigger, store=store)
        _loop.start()
        _runner_started = True
        log.info("ScheduleLoop started for host integration")
    except Exception as exc:
        log.debug("Schedule runner unavailable: %s", exc)
