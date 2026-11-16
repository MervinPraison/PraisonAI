"""Ensure SDK schedule runner + optional ScheduleLoop daemon."""

from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)
_runner_lock = threading.Lock()
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
    except ImportError as exc:
        # Truly optional feature: the scheduler package is not installed. This is
        # the ONLY leg that legitimately means "nothing to run", so DEBUG is fine.
        log.debug("Scheduler optional dependency not installed: %s", exc)
        return

    with _runner_lock:
        if _runner_started:
            return
        try:
            store = get_default_store()
            executor = _build_executor(store)

            # Only poll when we can actually execute. The canonical store claims a
            # due job *atomically* — advancing ``last_run_at`` and deleting one-shot
            # jobs at claim time (before the trigger runs). If we started the loop
            # with no executor and let ``on_trigger`` raise, ``fire_due`` would still
            # have consumed the occurrence (the claim persisted the advance), losing
            # one-shot and long-interval work. So when no executor can be built we
            # leave the loop unstarted — nothing is claimed, every job stays truly
            # due until a later start finds an executor (issue #4079, Defect 2).
            if executor is None:
                log.warning(
                    "Schedule executor unavailable; poll loop not started. "
                    "Scheduled jobs will remain due but will NOT fire until the "
                    "host app is restarted with the executor available."
                )
                return

            from praisonai._async_bridge import run_sync_or_offload

            # Bind the executor at definition time so a later reset of the
            # module global (e.g. stop_schedule_runner) cannot break a tick.
            def on_trigger(job, _executor=executor):
                log.info("Schedule triggered: %s", getattr(job, "name", job))
                # ScheduleLoop claims the occurrence *atomically* before this fires
                # (advancing last_run_at / deleting one-shot jobs at claim time). The
                # prior ``asyncio.run(...)`` path had no timeout, so a legitimately
                # long-running scheduled agent/command always completed. Pass
                # ``timeout=None`` to keep that unbounded behaviour — the bridge's
                # default 300s would otherwise cancel long runs *after* the claim,
                # silently dropping one-shot and long-interval work.
                run_sync_or_offload(
                    _executor._execute_one(job),
                    timeout=None,
                    thread_name="praisonai-schedule-tick",
                )

            loop = ScheduleLoop(on_trigger=on_trigger, store=store)
            loop.start()
            _executor = executor
            _loop = loop
            _runner_started = True
            log.info("ScheduleLoop started for host integration")
        except Exception:
            # A real failure (store construction, thread creation, executor init):
            # the operator MUST see the traceback because scheduling is now off and
            # _runner_started stays False, so scheduled jobs never fire silently.
            log.exception(
                "Schedule runner failed to start; scheduled jobs will NOT fire "
                "until the host app is restarted."
            )


def stop_schedule_runner(timeout: float = 5.0) -> None:
    """Stop the ScheduleLoop started by :func:`ensure_schedule_runner`.

    Idempotent; lets host embedders that rebuild their app release the poll
    thread instead of leaking it. A later ``ensure_schedule_runner()`` call
    starts a fresh loop.
    """
    global _runner_started, _loop, _executor
    with _runner_lock:
        loop, _loop = _loop, None
        _executor = None
        _runner_started = False
    if loop is not None:
        try:
            loop.stop(timeout=timeout)
        except Exception:
            log.exception("ScheduleLoop stop failed")
