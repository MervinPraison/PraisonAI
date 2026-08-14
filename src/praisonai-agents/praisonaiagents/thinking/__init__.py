"""
Extended Thinking Budgets Module for PraisonAI Agents.

Provides configurable thinking budgets for LLM reasoning:
- Token budgets for extended thinking
- Time budgets for reasoning
- Adaptive budget allocation
- Budget tracking and reporting

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- Budgets only applied when configured
- No overhead when not in use

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.thinking import ThinkingBudget

    # Create a thinking budget (helper for computing per-task token limits)
    budget = ThinkingBudget(
        max_tokens=16000,
        max_time_seconds=60,
        adaptive=True
    )

    # Compute an adaptive token budget for a given task complexity (0.0-1.0)
    tokens = budget.get_tokens_for_complexity(0.8)

    # Note: `agent.thinking_budget` stores this object on the agent as a hint,
    # but the core Agent request pipeline does not yet apply it automatically.
    # To influence step-by-step reasoning today, use the built-in
    # `reasoning_steps` option instead:
    agent = Agent(instructions="...", reasoning_steps=True)
"""

__all__ = [
    # Core classes
    "ThinkingBudget",
    "ThinkingConfig",
    # Tracking
    "ThinkingUsage",
    "ThinkingTracker",
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name == "ThinkingBudget":
        from .budget import ThinkingBudget
        return ThinkingBudget
    
    if name == "ThinkingConfig":
        from .config import ThinkingConfig
        return ThinkingConfig
    
    if name == "ThinkingUsage":
        from .tracker import ThinkingUsage
        return ThinkingUsage
    
    if name == "ThinkingTracker":
        from .tracker import ThinkingTracker
        return ThinkingTracker
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
