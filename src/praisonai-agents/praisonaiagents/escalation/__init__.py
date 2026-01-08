"""
Escalation Module for PraisonAI Agents.

Provides progressive escalation pipeline for auto-mode execution:
- Stage 0: Direct response (no tools, no planning)
- Stage 1: Heuristic tool usage (local signals, no extra LLM call)
- Stage 2: Lightweight plan (single LLM call, constrained)
- Stage 3: Full autonomous loop (tools + subagents + verification)

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- Escalation only triggered when signals indicate need
- No overhead for simple tasks

Usage:
    from praisonaiagents.escalation import EscalationPipeline, EscalationStage
    
    pipeline = EscalationPipeline()
    stage = pipeline.analyze(prompt, context)
    result = await pipeline.execute(prompt, stage)
"""

__all__ = [
    # Core pipeline
    "EscalationPipeline",
    "EscalationStage",
    "EscalationConfig",
    # Signals and triggers
    "EscalationSignal",
    "EscalationTrigger",
    # Results
    "EscalationResult",
    # Doom loop detection
    "DoomLoopDetector",
    "DoomLoopConfig",
    # Observability
    "ObservabilityHooks",
    "EventType",
    "ExecutionMetrics",
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name == "EscalationPipeline":
        from .pipeline import EscalationPipeline
        return EscalationPipeline
    
    if name == "EscalationStage":
        from .types import EscalationStage
        return EscalationStage
    
    if name == "EscalationConfig":
        from .types import EscalationConfig
        return EscalationConfig
    
    if name == "EscalationSignal":
        from .types import EscalationSignal
        return EscalationSignal
    
    if name == "EscalationTrigger":
        from .triggers import EscalationTrigger
        return EscalationTrigger
    
    if name == "EscalationResult":
        from .types import EscalationResult
        return EscalationResult
    
    if name == "DoomLoopDetector":
        from .doom_loop import DoomLoopDetector
        return DoomLoopDetector
    
    if name == "CheckpointEvent":
        from .types import CheckpointEvent
        return CheckpointEvent
    
    if name == "DoomLoopConfig":
        from .doom_loop import DoomLoopConfig
        return DoomLoopConfig
    
    if name == "ObservabilityHooks":
        from .observability import ObservabilityHooks
        return ObservabilityHooks
    
    if name == "EventType":
        from .observability import EventType
        return EventType
    
    if name == "ExecutionMetrics":
        from .observability import ExecutionMetrics
        return ExecutionMetrics
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
