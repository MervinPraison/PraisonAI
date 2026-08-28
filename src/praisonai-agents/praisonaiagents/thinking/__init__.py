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

    # `agent.thinking_budget` is a backward-compatible alias for the unified
    # `reasoning_effort` control. Prefer the graded level directly, which the
    # core request pipeline translates to each provider's native parameter
    # (OpenAI/xAI `reasoning_effort`, Anthropic/Gemini extended-thinking budget):
    agent = Agent(instructions="...", reasoning_effort="high")
"""

__all__ = [
    # Core classes
    "ThinkingBudget",
    "ThinkingConfig",
    # Tracking
    "ThinkingUsage",
    "ThinkingTracker",
    # Reasoning-effort translation (provider-portable)
    "resolve_reasoning_params",
    "normalize_effort",
    "EFFORT_LEVELS",
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

    if name in ("resolve_reasoning_params", "normalize_effort", "EFFORT_LEVELS"):
        from . import effort
        return getattr(effort, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
