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

Default storage: ~/.praisonai/config.yaml (under ``schedules`` key)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Schedule, ScheduleJob, DeliveryTarget, RunRecord
    from .store import FileScheduleStore
    from .config_store import ConfigYamlScheduleStore
    from .parser import parse_schedule
    from .runner import ScheduleRunner
    from .loop import ScheduleLoop
    from .protocols import ScheduleStoreProtocol, JobConditionProtocol, GateResult

_module_cache = {}


def __getattr__(name: str):
    """Lazy load scheduler components."""
    if name in _module_cache:
        return _module_cache[name]

    if name in ("Schedule", "ScheduleJob", "DeliveryTarget", "RunRecord"):
        from .models import Schedule, ScheduleJob, DeliveryTarget, RunRecord
        _module_cache["Schedule"] = Schedule
        _module_cache["ScheduleJob"] = ScheduleJob
        _module_cache["DeliveryTarget"] = DeliveryTarget
        _module_cache["RunRecord"] = RunRecord
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

    if name == "ScheduleLoop":
        from .loop import ScheduleLoop
        _module_cache[name] = ScheduleLoop
        return ScheduleLoop

    if name == "ConfigYamlScheduleStore":
        from .config_store import ConfigYamlScheduleStore
        _module_cache[name] = ConfigYamlScheduleStore
        return ConfigYamlScheduleStore

    if name in ("ScheduleStoreProtocol", "JobConditionProtocol", "GateResult"):
        from .protocols import (
            ScheduleStoreProtocol,
            JobConditionProtocol,
            GateResult,
        )
        _module_cache["ScheduleStoreProtocol"] = ScheduleStoreProtocol
        _module_cache["JobConditionProtocol"] = JobConditionProtocol
        _module_cache["GateResult"] = GateResult
        return _module_cache[name]

    if name in ("Blueprint", "BlueprintSlot", "BlueprintStoreProtocol"):
        from .blueprint_defs import Blueprint, BlueprintSlot, BlueprintStoreProtocol
        _module_cache["Blueprint"] = Blueprint
        _module_cache["BlueprintSlot"] = BlueprintSlot
        _module_cache["BlueprintStoreProtocol"] = BlueprintStoreProtocol
        return _module_cache[name]

    if name in ("Suggestion", "SuggestionStore", "MAX_PENDING_CAP"):
        from .suggestion_store import Suggestion, SuggestionStore, MAX_PENDING_CAP
        _module_cache["Suggestion"] = Suggestion
        _module_cache["SuggestionStore"] = SuggestionStore
        _module_cache["MAX_PENDING_CAP"] = MAX_PENDING_CAP
        return _module_cache[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Schedule",
    "ScheduleJob",
    "DeliveryTarget",
    "RunRecord",
    "FileScheduleStore",
    "ConfigYamlScheduleStore",
    "parse_schedule",
    "ScheduleRunner",
    "ScheduleLoop",
    "ScheduleStoreProtocol",
    "JobConditionProtocol",
    "GateResult",
    "Blueprint",
    "BlueprintSlot",
    "BlueprintStoreProtocol",
    "Suggestion",
    "SuggestionStore",
    "MAX_PENDING_CAP",
]
