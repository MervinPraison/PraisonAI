"""Lifecycle hook emission for schedule mutations.

``HookEvent.SCHEDULE_ADD`` / ``HookEvent.SCHEDULE_REMOVE`` are emitted from the
schedule store because the store is the one point every author/deleter path
funnels through:

* the agent-callable ``schedule_add`` / ``schedule_remove`` tools,
* ``praisonai schedule add`` (delegates to the tool) and ``praisonai schedule
  remove`` / ``delete`` (call ``store.remove(job_id)`` directly),
* the gateway's ``config.yaml`` schedule reconciler,
* the automatic cleanup of a spent ``delete_after_run`` one-shot.

Emitting per-call-site instead would have silently missed most of those.

Everything here is best-effort: a hook must never break, slow down, or roll
back the mutation it observes, and there is no measurable cost when nothing is
registered (a single ``has_hooks`` dictionary lookup).
"""

import asyncio
import os
import time
from typing import Any, Optional, Set

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)

# Strong references to in-flight fire-and-forget hook tasks. Without this the
# event loop only holds a weak reference and a task may be garbage-collected
# before it completes (see asyncio.create_task docs). Mirrors the gateway's
# ``praisonai_bot.bots._protocol_mixin`` emitter.
_PENDING_HOOK_TASKS: Set[Any] = set()


def _on_hook_task_done(task: Any) -> None:
    """Drop the finished task and log any swallowed coroutine exception."""
    _PENDING_HOOK_TASKS.discard(task)
    try:
        exc = task.exception()
    except Exception:  # noqa: BLE001 — cancelled or loop teardown; nothing to log
        return
    if exc is not None:
        logger.debug("schedule hook task error (non-fatal): %s", exc)


def describe_schedule(schedule: Any) -> str:
    """Render a job's schedule as a short, stable, human-readable token."""
    try:
        kind = getattr(schedule, "kind", "")
        if kind == "every" and getattr(schedule, "every_seconds", None):
            return f"every {schedule.every_seconds}s"
        if kind == "cron" and getattr(schedule, "cron_expr", None):
            return f"cron:{schedule.cron_expr}"
        if kind == "at" and getattr(schedule, "at", None):
            return f"at:{schedule.at}"
        return str(kind or "")
    except Exception:  # pragma: no cover - defensive
        return ""


def _dispatch(event: Any, input_data: Any, registry: Any) -> None:
    """Run hooks for ``event``, working in both sync and async contexts.

    ``HookRunner.execute_sync`` raises inside a running event loop, so when one
    is detected the coroutine is scheduled fire-and-forget instead. Never
    raises to the caller.
    """
    from ..hooks.runner import HookRunner

    runner = HookRunner(registry)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        task = loop.create_task(runner.execute(event, input_data))
        _PENDING_HOOK_TASKS.add(task)
        task.add_done_callback(_on_hook_task_done)
    else:
        runner.execute_sync(event, input_data)


def _registry_for(event: Any) -> Optional[Any]:
    """Return the default hook registry only when it has hooks for ``event``."""
    from ..hooks.registry import get_default_registry

    registry = get_default_registry()
    return registry if registry.has_hooks(event) else None


def emit_schedule_add(job: Any) -> None:
    """Fire ``SCHEDULE_ADD`` for a newly persisted job (best-effort)."""
    try:
        from ..hooks.types import HookEvent

        registry = _registry_for(HookEvent.SCHEDULE_ADD)
        if registry is None:
            return

        from ..hooks.events import ScheduleAddInput

        _dispatch(
            HookEvent.SCHEDULE_ADD,
            ScheduleAddInput(
                session_id="",
                cwd=os.getcwd(),
                event_name=HookEvent.SCHEDULE_ADD.value,
                timestamp=str(time.time()),
                agent_name=getattr(job, "agent_id", None) or "scheduler",
                job_name=getattr(job, "name", "") or "",
                job_id=str(getattr(job, "id", "") or ""),
                schedule=describe_schedule(getattr(job, "schedule", None)),
                message=getattr(job, "message", "") or "",
                agent_id=getattr(job, "agent_id", "") or "",
                principal=getattr(job, "principal", "") or "",
                enabled=bool(getattr(job, "enabled", True)),
            ),
            registry,
        )
    except Exception:  # noqa: BLE001 — observability must never break the store
        logger.debug("SCHEDULE_ADD hook emit failed (non-fatal)", exc_info=True)


def emit_schedule_remove(job: Any) -> None:
    """Fire ``SCHEDULE_REMOVE`` for a job that was actually deleted."""
    try:
        from ..hooks.types import HookEvent

        registry = _registry_for(HookEvent.SCHEDULE_REMOVE)
        if registry is None:
            return

        from ..hooks.events import ScheduleRemoveInput

        _dispatch(
            HookEvent.SCHEDULE_REMOVE,
            ScheduleRemoveInput(
                session_id="",
                cwd=os.getcwd(),
                event_name=HookEvent.SCHEDULE_REMOVE.value,
                timestamp=str(time.time()),
                agent_name=getattr(job, "agent_id", None) or "scheduler",
                job_name=getattr(job, "name", "") or "",
                job_id=str(getattr(job, "id", "") or ""),
                schedule=describe_schedule(getattr(job, "schedule", None)),
                principal=getattr(job, "principal", "") or "",
            ),
            registry,
        )
    except Exception:  # noqa: BLE001 — observability must never break the store
        logger.debug("SCHEDULE_REMOVE hook emit failed (non-fatal)", exc_info=True)
