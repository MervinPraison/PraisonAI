#!/usr/bin/env python3
"""
Basic Thinking Budgets Example for PraisonAI Agents.

This example demonstrates how to use thinking budgets with Agent:
1. Create an Agent with thinking budget
2. Use predefined budget levels
3. Track thinking usage

Usage:
    python basic_thinking.py
"""

from praisonaiagents import Agent
from praisonaiagents.thinking import ThinkingBudget, ThinkingTracker
from praisonaiagents.thinking.budget import BudgetLevel


def main():
    print("=" * 60)
    print("Agent-Centric Thinking Budgets Demo")
    print("=" * 60)
    
    # ==========================================================================
    # Budget Levels
    # ==========================================================================
    print("\n--- Available Budget Levels ---")
    
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
    # Agent with Thinking Budget
    # ==========================================================================
    print("\n--- Creating Agent with Thinking Budget ---")
    
    agent = Agent(
        name="DeepThinker",
        instructions="You are a problem-solving assistant that thinks step by step.",
        thinking_budget=ThinkingBudget.high()  # 16,000 tokens for reasoning
    )
    
    print(f"Agent: {agent.name}")
    print(f"Thinking budget: {agent.thinking_budget.max_tokens:,} tokens")
    print(f"Adaptive: {agent.thinking_budget.adaptive}")
    
    # ==========================================================================
    # Custom Budget
    # ==========================================================================
    print("\n--- Custom Thinking Budget ---")
    
    custom_budget = ThinkingBudget(
        max_tokens=12000,
        min_tokens=2000,
        adaptive=True,
        max_time_seconds=120.0
    )
    
    agent_custom = Agent(
        name="CustomThinker",
        instructions="You solve complex problems.",
        thinking_budget=custom_budget
    )
    
    print(f"Agent: {agent_custom.name}")
    print(f"Max tokens: {agent_custom.thinking_budget.max_tokens:,}")
    print(f"Min tokens: {agent_custom.thinking_budget.min_tokens:,}")
    print(f"Time limit: {agent_custom.thinking_budget.max_time_seconds}s")
    
    # ==========================================================================
    # Complexity-Based Scaling
    # ==========================================================================
    print("\n--- Complexity-Based Token Allocation ---")
    
    budget = agent.thinking_budget
    complexities = [0.0, 0.25, 0.5, 0.75, 1.0]
    for complexity in complexities:
        tokens = budget.get_tokens_for_complexity(complexity)
        bar = "█" * int(tokens / 1000)
        print(f"  Complexity {complexity:.2f}: {tokens:,} tokens {bar}")
    
    # ==========================================================================
    # Usage Tracking
    # ==========================================================================
    print("\n--- Session Tracking ---")
    
    tracker = ThinkingTracker()
    
    # Simulate thinking sessions
    sessions = [
        (8000, 4000, 20.0),
        (8000, 6000, 35.0),
        (16000, 12000, 60.0),
    ]
    
    for budget_tokens, tokens_used, time_seconds in sessions:
        session = tracker.start_session(budget_tokens=budget_tokens)
        tracker.end_session(session, tokens_used=tokens_used, time_seconds=time_seconds)
    
    summary = tracker.get_summary()
    print(f"  Total sessions: {summary['session_count']}")
    print(f"  Total tokens used: {summary['total_tokens_used']:,}")
    print(f"  Average utilization: {summary['average_utilization']:.1%}")
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
