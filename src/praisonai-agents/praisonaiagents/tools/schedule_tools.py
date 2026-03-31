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
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)

# ── lazy singleton store ─────────────────────────────────────────────────────

_store_instance = None

def set_store(store):
    """Inject an external schedule store (e.g., config.yaml-backed).

    When PraisonAIUI is running, it calls this at startup to redirect
    all agent schedule_add/list/remove operations to the unified
    ``config.yaml`` instead of the default ``jobs.json``.
    """
    global _store_instance
    _store_instance = store

def _get_store():
    """Return (or create) the global schedule store.

    Uses ``ConfigYamlScheduleStore`` (config.yaml) by default.
    Automatically migrates any existing ``jobs.json`` data on first use.
    """
    global _store_instance
    if _store_instance is None:
        from ..scheduler.config_store import ConfigYamlScheduleStore
        _store_instance = ConfigYamlScheduleStore()
        _store_instance.migrate_from_json()
    return _store_instance

# ── tools ────────────────────────────────────────────────────────────────────

def schedule_add(
    name: str,
    schedule: str,
    message: str = "",
    channel: str = "",
    channel_id: str = "",
    agent_id: str = "",
    session_id: str = "",
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
        channel: Delivery platform ("telegram", "discord", "slack",
                 "whatsapp"). If set with channel_id, the result will
                 be sent back to that chat when the job fires.
        channel_id: Target chat/channel/group ID on the platform.
        agent_id: Which agent should execute this job. If empty, the
                  executor uses its default agent.
        session_id: Optional session ID to preserve conversation context.
                    If set, the agent will have access to prior chat history.

    Returns:
        Confirmation string with the job id.
    """
    try:
        from ..scheduler.parser import parse_schedule
        from ..scheduler.models import ScheduleJob, DeliveryTarget

        sched = parse_schedule(schedule)

        delivery = None
        if channel and channel_id:
            delivery = DeliveryTarget(
                channel=channel,
                channel_id=channel_id,
                session_id=session_id or None,
            )

        job = ScheduleJob(
            name=name,
            schedule=sched,
            message=message,
            agent_id=agent_id or None,
            delivery=delivery,
        )

        store = _get_store()

        # Prevent duplicate names
        existing = store.get_by_name(name)
        if existing:
            return f"A schedule named '{name}' already exists (id: {existing.id}). Remove it first or choose a different name."

        store.add(job)
        delivery_note = f" → deliver to {channel}:{channel_id}" if delivery else ""
        agent_note = f" agent={agent_id}" if agent_id else ""
        return f"Schedule '{name}' added (id: {job.id}, {schedule}{agent_note}{delivery_note})."
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

            parts = [f"  - {j.name} (id: {j.id}) [{status}] — {sched_str}"]
            if j.agent_id:
                parts.append(f" agent={j.agent_id}")
            if j.delivery:
                parts.append(f" → {j.delivery.channel}:{j.delivery.channel_id}")
            if j.message:
                parts.append(f' — "{j.message}"')
            lines.append("".join(parts))
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
