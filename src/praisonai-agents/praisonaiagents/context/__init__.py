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

def format_percent(value: float) -> str:
    """
    Smart percentage formatting for context utilization display.
    
    - For values < 0.1%: shows "<0.1%"
    - For values < 1%: shows 2 decimal places (e.g., "0.02%")
    - For values >= 1%: shows 1 decimal place (e.g., "5.3%")
    
    Args:
        value: A ratio (0.0 to 1.0+), NOT already multiplied by 100
        
    Returns:
        Formatted percentage string
    """
    pct = value * 100
    if pct < 0.1 and pct > 0:
        return "<0.1%"
    elif pct < 1.0:
        return f"{pct:.2f}%"
    else:
        return f"{pct:.1f}%"


__all__ = [
    # Utilities
    "format_percent",
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
    "LLMSummarizeOptimizer",
    "SmartOptimizer",
    "get_optimizer",
    "get_effective_history",
    # Monitoring
    "ContextMonitor",
    "MultiAgentMonitor",
    "redact_sensitive",
    "format_human_snapshot",
    "format_json_snapshot",
    "validate_monitor_path",
    "should_include_content",
    "load_ignore_patterns",
    # Manager Facade (NEW)
    "ContextManager",
    "MultiAgentContextManager",
    "create_context_manager",
    "ManagerConfig",
    "ContextPolicy",
    "EstimationMode",
    "ContextShareMode",
    "ToolShareMode",
    "OptimizationEvent",
    "OptimizationEventType",
    "EstimationMetrics",
    "PerToolBudget",
    "SnapshotHookData",
    "SessionDeduplicationCache",
    # Protocols (NEW)
    "ContextView",
    "ContextMutator",
    "ContextMessage",
    "MessageMetadata",
    "MessageRole",
    "validate_message_schema",
    "get_effective_history",
    "cleanup_orphaned_parents",
    # Store (NEW)
    "ContextStoreImpl",
    "ContextViewImpl",
    "ContextMutatorImpl",
    "AgentBudget",
    "get_global_store",
    "reset_global_store",
    # Instrumentation (NEW)
    "ContextMetrics",
    "get_metrics",
    "reset_metrics",
    "context_operation",
    "timed_section",
    "log_context_size",
    "log_optimization_event",
    "run_benchmark",
    "BenchmarkResult",
    "format_benchmark_results",
    # Fast Context (legacy)
    "FastContext",
    "FastContextResult",
    "FileMatch",
    "LineRange",
    # Artifacts (Dynamic Context Discovery)
    "ArtifactRef",
    "ArtifactMetadata",
    "GrepMatch",
    "QueueConfig",
    "ArtifactStoreProtocol",
    "HistoryStoreProtocol",
    "TerminalLoggerProtocol",
    "compute_checksum",
    "generate_summary",
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
                "LLMSummarizeOptimizer", "SmartOptimizer", "get_optimizer"):
        from . import optimizer
        return getattr(optimizer, name)
    
    # Monitoring
    if name in ("ContextMonitor", "MultiAgentMonitor", "redact_sensitive",
                "format_human_snapshot", "format_json_snapshot",
                "validate_monitor_path", "should_include_content", "load_ignore_patterns"):
        from . import monitor
        return getattr(monitor, name)
    
    # Manager Facade
    if name in ("ContextManager", "MultiAgentContextManager", "create_context_manager",
                "ManagerConfig", "ContextPolicy", "EstimationMode", "ContextShareMode",
                "ToolShareMode", "OptimizationEvent", "OptimizationEventType",
                "EstimationMetrics", "PerToolBudget", "SnapshotHookData",
                "SessionDeduplicationCache"):
        from . import manager
        return getattr(manager, name)
    
    # Protocols
    if name in ("ContextView", "ContextMutator", "ContextMessage",
                "MessageMetadata", "MessageRole", "validate_message_schema",
                "cleanup_orphaned_parents"):
        from . import protocols
        return getattr(protocols, name)
    
    # get_effective_history from protocols (not optimizer)
    if name == "get_effective_history":
        from .protocols import get_effective_history
        return get_effective_history
    
    # Store
    if name in ("ContextStoreImpl", "ContextViewImpl", "ContextMutatorImpl",
                "AgentBudget", "get_global_store", "reset_global_store"):
        from . import store
        return getattr(store, name)
    
    # Instrumentation
    if name in ("ContextMetrics", "get_metrics", "reset_metrics",
                "context_operation", "timed_section", "log_context_size",
                "log_optimization_event", "run_benchmark", "BenchmarkResult",
                "format_benchmark_results"):
        from . import instrumentation
        return getattr(instrumentation, name)
    
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
    
    # Artifacts (Dynamic Context Discovery)
    if name in ("ArtifactRef", "ArtifactMetadata", "GrepMatch", "QueueConfig",
                "ArtifactStoreProtocol", "HistoryStoreProtocol", "TerminalLoggerProtocol",
                "compute_checksum", "generate_summary"):
        from . import artifacts
        return getattr(artifacts, name)
    
    # Session Context Tracking (Agno pattern)
    if name in ("SessionContextTracker", "SessionState"):
        from . import session_tracker
        return getattr(session_tracker, name)
    
    # Context Aggregation (CrewAI pattern)
    if name in ("ContextAggregator", "AggregatedContext", "create_aggregator_from_config"):
        from . import aggregator
        return getattr(aggregator, name)
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
