"""
Scheduler module for PraisonAI Agents.

Provides agent-centric scheduling via tools — agents can add, list,
and remove scheduled jobs without any changes to the Agent class.

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.tools import schedule_add, schedule_list, schedule_remove

    agent = Agent(
        name="assistant",
        tools=[schedule_add, schedule_list, schedule_remove],
    )
    agent.start("Remind me to check email every morning at 7am")

Default storage: ~/.praisonai/schedules/jobs.json
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Schedule, ScheduleJob
    from .store import FileScheduleStore
    from .parser import parse_schedule
    from .runner import ScheduleRunner

_module_cache = {}


def __getattr__(name: str):
    """Lazy load scheduler components."""
    if name in _module_cache:
        return _module_cache[name]

    if name in ("Schedule", "ScheduleJob"):
        from .models import Schedule, ScheduleJob
        _module_cache["Schedule"] = Schedule
        _module_cache["ScheduleJob"] = ScheduleJob
        return _module_cache[name]

    if name == "FileScheduleStore":
        from .store import FileScheduleStore
        _module_cache[name] = FileScheduleStore
        return FileScheduleStore

    if name == "parse_schedule":
        from .parser import parse_schedule
        _module_cache[name] = parse_schedule
        return parse_schedule

    if name == "ScheduleRunner":
        from .runner import ScheduleRunner
        _module_cache[name] = ScheduleRunner
        return ScheduleRunner

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Schedule",
    "ScheduleJob",
    "FileScheduleStore",
    "parse_schedule",
    "ScheduleRunner",
]
