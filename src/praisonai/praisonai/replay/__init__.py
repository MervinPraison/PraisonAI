"""
Replay Module for PraisonAI.

Provides context replay functionality for debugging and analysis.
Allows stepping through agent execution context changes.

Usage:
    from praisonai.replay import ContextTraceWriter, ContextTraceReader, ReplayPlayer
    
    # Write traces during execution
    writer = ContextTraceWriter(session_id="my-session")
    writer.emit(event)
    writer.close()
    
    # Read and replay traces
    reader = ContextTraceReader("~/.praison/traces/my-session.jsonl")
    for event in reader:
        print(event)
    
    # Interactive replay
    player = ReplayPlayer(reader)
    player.run()

    # Record a run (PraisonAI Replay) and export it
    from praisonai.replay import record
    from praisonai.replay.events import load_events
    from praisonai.replay import export

    with record(live=True) as rec:
        agent.start("Say hello")
    html = export.to_html(load_events(rec.path))
"""

__all__ = [
    "record",
    "Recording",
    "TraceStepCache",
    "load_events",
    "ContextTraceWriter",
    "ContextTraceReader",
    "ReplayPlayer",
    "get_traces_dir",
    "list_traces",
    "ContextEffectivenessJudge",
    "JudgeReport",
    "format_judge_report",
    "generate_plan_from_report",
    "JudgePlan",
    "ActionableFix",
    "PlanApplier",
]


def __getattr__(name: str):
    """Lazy load module components."""
    if name in ("record", "Recording"):
        from . import recorder
        return getattr(recorder, name)

    if name == "TraceStepCache":
        from .rerun import TraceStepCache
        return TraceStepCache

    if name == "load_events":
        from .events import load_events
        return load_events

    if name == "ContextTraceWriter":
        from .writer import ContextTraceWriter
        return ContextTraceWriter
    
    if name == "ContextTraceReader":
        from .reader import ContextTraceReader
        return ContextTraceReader
    
    if name == "ReplayPlayer":
        from .player import ReplayPlayer
        return ReplayPlayer
    
    if name == "get_traces_dir":
        from .storage import get_traces_dir
        return get_traces_dir
    
    if name == "list_traces":
        from .storage import list_traces
        return list_traces
    
    if name == "ContextEffectivenessJudge":
        from .judge import ContextEffectivenessJudge
        return ContextEffectivenessJudge
    
    if name == "JudgeReport":
        from .judge import JudgeReport
        return JudgeReport
    
    if name == "format_judge_report":
        from .judge import format_judge_report
        return format_judge_report
    
    if name == "generate_plan_from_report":
        from .judge import generate_plan_from_report
        return generate_plan_from_report
    
    if name == "JudgePlan":
        from .plan import JudgePlan
        return JudgePlan
    
    if name == "ActionableFix":
        from .plan import ActionableFix
        return ActionableFix
    
    if name == "PlanApplier":
        from .applier import PlanApplier
        return PlanApplier
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
