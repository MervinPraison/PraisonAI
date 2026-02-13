"""
Schedule tools for PraisonAI Agents.

Agent-centric scheduling — agents call these tools to add, list, and
remove scheduled jobs.  No changes to the Agent class required.

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.tools import schedule_add, schedule_list, schedule_remove

    agent = Agent(
        name="assistant",
        instructions="You can set reminders and schedules for the user.",
        tools=[schedule_add, schedule_list, schedule_remove],
    )
    agent.start("Remind me to check email every morning at 7am")
"""

import logging

logger = logging.getLogger(__name__)

# ── lazy singleton store ─────────────────────────────────────────────────────

_store_instance = None


def _get_store():
    """Return (or create) the global ``FileScheduleStore``."""
    global _store_instance
    if _store_instance is None:
        from ..scheduler.store import FileScheduleStore
        _store_instance = FileScheduleStore()
    return _store_instance


# ── tools ────────────────────────────────────────────────────────────────────


def schedule_add(
    name: str,
    schedule: str,
    message: str = "",
) -> str:
    """Add a new scheduled job.

    Args:
        name: Human-readable name for this schedule (e.g. "morning-email-check").
        schedule: When to run. Accepted formats:
            - "hourly", "daily"
            - "*/30m", "*/6h", "*/10s"  (interval)
            - "cron:0 7 * * *"          (cron expression)
            - "at:2026-03-01T09:00:00"  (one-shot ISO timestamp)
            - "in 20 minutes"           (relative one-shot)
        message: The prompt or reminder text to deliver when triggered.

    Returns:
        Confirmation string with the job id.
    """
    try:
        from ..scheduler.parser import parse_schedule
        from ..scheduler.models import ScheduleJob

        sched = parse_schedule(schedule)
        job = ScheduleJob(name=name, schedule=sched, message=message)

        store = _get_store()

        # Prevent duplicate names
        existing = store.get_by_name(name)
        if existing:
            return f"A schedule named '{name}' already exists (id: {existing.id}). Remove it first or choose a different name."

        store.add(job)
        return f"Schedule '{name}' added (id: {job.id}, {schedule})."
    except ValueError as e:
        return f"Error adding schedule: {e}"
    except Exception as e:
        logger.error("schedule_add failed: %s", e, exc_info=True)
        return f"Error adding schedule: {e}"


def schedule_list() -> str:
    """List all scheduled jobs.

    Returns:
        A formatted string listing every job with its id, name, schedule,
        status, and message.  Returns a friendly message when empty.
    """
    try:
        store = _get_store()
        jobs = store.list()
        if not jobs:
            return "No schedules found. Use schedule_add to create one."

        lines = [f"Found {len(jobs)} schedule(s):\n"]
        for j in jobs:
            status = "enabled" if j.enabled else "disabled"
            sched = j.schedule
            if sched.kind == "every" and sched.every_seconds:
                sched_str = _human_interval(sched.every_seconds)
            elif sched.kind == "cron":
                sched_str = f"cron: {sched.cron_expr}"
            elif sched.kind == "at":
                sched_str = f"at: {sched.at}"
            else:
                sched_str = str(sched.kind)
            lines.append(
                f"  - {j.name} (id: {j.id}) [{status}] — {sched_str}"
                + (f" — \"{j.message}\"" if j.message else "")
            )
        return "\n".join(lines)
    except Exception as e:
        logger.error("schedule_list failed: %s", e, exc_info=True)
        return f"Error listing schedules: {e}"


def schedule_remove(name: str) -> str:
    """Remove a scheduled job by name.

    Args:
        name: The name of the schedule to remove.

    Returns:
        Confirmation or not-found message.
    """
    try:
        store = _get_store()
        removed = store.remove_by_name(name)
        if removed:
            return f"Schedule '{name}' removed."
        return f"Schedule '{name}' not found."
    except Exception as e:
        logger.error("schedule_remove failed: %s", e, exc_info=True)
        return f"Error removing schedule: {e}"


# ── helpers ──────────────────────────────────────────────────────────────────


def _human_interval(seconds: int) -> str:
    """Convert seconds to a human-friendly string."""
    if seconds >= 86400 and seconds % 86400 == 0:
        d = seconds // 86400
        return f"every {d} day(s)"
    if seconds >= 3600 and seconds % 3600 == 0:
        h = seconds // 3600
        return f"every {h} hour(s)"
    if seconds >= 60 and seconds % 60 == 0:
        m = seconds // 60
        return f"every {m} minute(s)"
    return f"every {seconds} second(s)"
