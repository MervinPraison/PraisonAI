"""Ensure SDK schedule runner + optional ScheduleLoop daemon."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)
_runner_started = False
_loop = None


def ensure_schedule_runner() -> None:
    """Lazy-init FileScheduleStore-backed runner and optional ScheduleLoop."""
    global _runner_started, _loop
    if _runner_started:
        return
    try:
        from praisonaiagents.scheduler import FileScheduleStore, ScheduleLoop

        store = FileScheduleStore()

        def on_trigger(job):
            log.info("Schedule triggered: %s", getattr(job, "name", job))

        _loop = ScheduleLoop(on_trigger=on_trigger, store=store)
        _loop.start()
        _runner_started = True
        log.info("ScheduleLoop started for host integration")
    except Exception as exc:
        log.debug("Schedule runner unavailable: %s", exc)
