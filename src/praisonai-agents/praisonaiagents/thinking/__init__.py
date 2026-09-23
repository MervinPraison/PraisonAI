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

from .._lazy import create_lazy_getattr

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


_LAZY_IMPORTS = {
    "ThinkingBudget": ("praisonaiagents.thinking.budget", "ThinkingBudget"),
    "ThinkingConfig": ("praisonaiagents.thinking.config", "ThinkingConfig"),
    "ThinkingUsage": ("praisonaiagents.thinking.tracker", "ThinkingUsage"),
    "ThinkingTracker": ("praisonaiagents.thinking.tracker", "ThinkingTracker"),
    "resolve_reasoning_params": ("praisonaiagents.thinking.effort", "resolve_reasoning_params"),
    "normalize_effort": ("praisonaiagents.thinking.effort", "normalize_effort"),
    "EFFORT_LEVELS": ("praisonaiagents.thinking.effort", "EFFORT_LEVELS"),
}

__getattr__ = create_lazy_getattr(_LAZY_IMPORTS, __name__)
