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
"""

__all__ = [
    "ContextTraceWriter",
    "ContextTraceReader",
    "ReplayPlayer",
    "get_traces_dir",
    "list_traces",
]


def __getattr__(name: str):
    """Lazy load module components."""
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
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
