"""
Context Management Module for PraisonAI Agents.

This module provides comprehensive context management capabilities:
- Token estimation and budgeting
- Context composition within limits
- Optimization strategies (truncate, sliding window, summarize, prune, smart)
- Real-time context monitoring
- Multi-agent context isolation

Also includes:
- Fast Context: Rapid parallel code search subagent

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- Features only activate when explicitly enabled
- No overhead when context management is not used

Usage:
    from praisonaiagents.context import (
        ContextBudgeter,
        ContextComposer,
        ContextMonitor,
        get_optimizer,
    )
    
    # Create budgeter for model
    budgeter = ContextBudgeter(model="gpt-4o")
    budget = budgeter.allocate()
    
    # Compose context within budget
    composer = ContextComposer(budget=budget)
    result = composer.compose(
        system_prompt="You are helpful",
        history=messages,
        tools=tool_schemas,
    )
    
    # Monitor context (opt-in)
    monitor = ContextMonitor(enabled=True)
    monitor.snapshot(ledger=result.ledger, budget=budget, messages=result.messages)
"""

__all__ = [
    # Models
    "ContextSegment",
    "ContextLedger",
    "BudgetAllocation",
    "ContextSnapshot",
    "OptimizerStrategy",
    "OptimizationResult",
    "MonitorConfig",
    "ContextConfig",
    # Token estimation
    "estimate_tokens_heuristic",
    "estimate_messages_tokens",
    "estimate_tool_schema_tokens",
    "TokenEstimatorImpl",
    "get_estimator",
    # Budgeting
    "ContextBudgeter",
    "get_model_limit",
    "get_output_reserve",
    # Ledger
    "ContextLedgerManager",
    "MultiAgentLedger",
    # Composition
    "ContextComposer",
    "ComposedContext",
    # Optimization
    "BaseOptimizer",
    "TruncateOptimizer",
    "SlidingWindowOptimizer",
    "PruneToolsOptimizer",
    "NonDestructiveOptimizer",
    "SummarizeOptimizer",
    "SmartOptimizer",
    "get_optimizer",
    "get_effective_history",
    # Monitoring
    "ContextMonitor",
    "MultiAgentMonitor",
    "redact_sensitive",
    "format_human_snapshot",
    "format_json_snapshot",
    # Fast Context (legacy)
    "FastContext",
    "FastContextResult",
    "FileMatch",
    "LineRange",
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    # Models
    if name in ("ContextSegment", "ContextLedger", "BudgetAllocation", 
                "ContextSnapshot", "OptimizerStrategy", "OptimizationResult",
                "MonitorConfig", "ContextConfig"):
        from . import models
        return getattr(models, name)
    
    # Token estimation
    if name in ("estimate_tokens_heuristic", "estimate_messages_tokens",
                "estimate_tool_schema_tokens", "TokenEstimatorImpl", "get_estimator"):
        from . import tokens
        return getattr(tokens, name)
    
    # Budgeting
    if name in ("ContextBudgeter", "get_model_limit", "get_output_reserve"):
        from . import budgeter
        return getattr(budgeter, name)
    
    # Ledger
    if name in ("ContextLedgerManager", "MultiAgentLedger"):
        from . import ledger
        return getattr(ledger, name)
    
    # Composition
    if name in ("ContextComposer", "ComposedContext"):
        from . import composer
        return getattr(composer, name)
    
    # Optimization
    if name in ("BaseOptimizer", "TruncateOptimizer", "SlidingWindowOptimizer",
                "PruneToolsOptimizer", "NonDestructiveOptimizer", "SummarizeOptimizer",
                "SmartOptimizer", "get_optimizer", "get_effective_history"):
        from . import optimizer
        return getattr(optimizer, name)
    
    # Monitoring
    if name in ("ContextMonitor", "MultiAgentMonitor", "redact_sensitive",
                "format_human_snapshot", "format_json_snapshot"):
        from . import monitor
        return getattr(monitor, name)
    
    # Fast Context (legacy)
    if name == "FastContext":
        from praisonaiagents.context.fast.fast_context import FastContext
        return FastContext
    if name == "FastContextResult":
        from praisonaiagents.context.fast.result import FastContextResult
        return FastContextResult
    if name == "FileMatch":
        from praisonaiagents.context.fast.result import FileMatch
        return FileMatch
    if name == "LineRange":
        from praisonaiagents.context.fast.result import LineRange
        return LineRange
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
