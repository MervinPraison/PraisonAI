#!/usr/bin/env python3
"""
Basic Thinking Budgets Example for PraisonAI Agents.

This example demonstrates how to use thinking budgets to:
1. Configure token budgets for extended thinking
2. Use predefined budget levels
3. Track thinking usage
4. Adapt budgets based on complexity

Usage:
    python basic_thinking.py
"""

from praisonaiagents.thinking import (
    ThinkingBudget, ThinkingConfig, ThinkingUsage, ThinkingTracker
)
from praisonaiagents.thinking.budget import BudgetLevel


def main():
    print("=" * 60)
    print("Thinking Budgets Demo")
    print("=" * 60)
    
    # ==========================================================================
    # Budget Levels
    # ==========================================================================
    print("\n--- Budget Levels ---")
    
    levels = [
        ("Minimal", ThinkingBudget.minimal()),
        ("Low", ThinkingBudget.low()),
        ("Medium", ThinkingBudget.medium()),
        ("High", ThinkingBudget.high()),
        ("Maximum", ThinkingBudget.maximum()),
    ]
    
    for name, budget in levels:
        print(f"  {name}: {budget.max_tokens:,} tokens")
    
    # ==========================================================================
    # Custom Budget
    # ==========================================================================
    print("\n--- Custom Budget ---")
    
    custom_budget = ThinkingBudget(
        max_tokens=12000,
        min_tokens=2000,
        adaptive=True,
        max_time_seconds=120.0
    )
    print(f"  Max tokens: {custom_budget.max_tokens:,}")
    print(f"  Min tokens: {custom_budget.min_tokens:,}")
    print(f"  Adaptive: {custom_budget.adaptive}")
    print(f"  Time limit: {custom_budget.max_time_seconds}s")
    
    # ==========================================================================
    # Complexity-Based Scaling
    # ==========================================================================
    print("\n--- Complexity-Based Token Allocation ---")
    
    budget = ThinkingBudget(
        max_tokens=16000,
        min_tokens=2000,
        adaptive=True
    )
    
    complexities = [0.0, 0.25, 0.5, 0.75, 1.0]
    for complexity in complexities:
        tokens = budget.get_tokens_for_complexity(complexity)
        bar = "█" * int(tokens / 1000)
        print(f"  Complexity {complexity:.2f}: {tokens:,} tokens {bar}")
    
    # ==========================================================================
    # Usage Tracking
    # ==========================================================================
    print("\n--- Usage Tracking ---")
    
    usage = ThinkingUsage(
        budget_tokens=8000,
        tokens_used=5000,
        time_seconds=30.0,
        budget_time=60.0
    )
    
    print(f"  Tokens used: {usage.tokens_used:,} / {usage.budget_tokens:,}")
    print(f"  Tokens remaining: {usage.tokens_remaining:,}")
    print(f"  Utilization: {usage.token_utilization:.1%}")
    print(f"  Over budget: {usage.is_over_budget}")
    print(f"  Time remaining: {usage.time_remaining}s")
    
    # ==========================================================================
    # Session Tracking
    # ==========================================================================
    print("\n--- Session Tracking ---")
    
    tracker = ThinkingTracker()
    
    # Simulate multiple thinking sessions
    sessions = [
        (8000, 4000, 20.0),
        (8000, 6000, 35.0),
        (16000, 12000, 60.0),
        (8000, 9000, 45.0),  # Over budget
    ]
    
    for budget_tokens, tokens_used, time_seconds in sessions:
        session = tracker.start_session(budget_tokens=budget_tokens)
        tracker.end_session(session, tokens_used=tokens_used, time_seconds=time_seconds)
    
    summary = tracker.get_summary()
    print(f"  Total sessions: {summary['session_count']}")
    print(f"  Total tokens used: {summary['total_tokens_used']:,}")
    print(f"  Average tokens/session: {summary['average_tokens_per_session']:,.0f}")
    print(f"  Average utilization: {summary['average_utilization']:.1%}")
    print(f"  Over-budget sessions: {summary['over_budget_count']}")
    
    # ==========================================================================
    # Serialization
    # ==========================================================================
    print("\n--- Serialization ---")
    
    budget = ThinkingBudget.from_level(BudgetLevel.HIGH)
    data = budget.to_dict()
    print(f"  Serialized: level={data['level']}, max_tokens={data['max_tokens']}")
    
    restored = ThinkingBudget.from_dict(data)
    print(f"  Restored: {restored.max_tokens:,} tokens")
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
