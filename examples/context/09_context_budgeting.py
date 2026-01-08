#!/usr/bin/env python3
"""
Context Budgeting Example

Demonstrates how to use context budgeting with Agent via context= param,
and also shows low-level ContextBudgeter usage for advanced scenarios.

Agent-Centric Quick Start:
    from praisonaiagents import Agent
    from praisonaiagents.context import ManagerConfig
    
    agent = Agent(
        instructions="You are helpful.",
        context=ManagerConfig(output_reserve=16000),  # Custom output reserve
    )
"""

from praisonaiagents import Agent
from praisonaiagents.context import (
    ManagerConfig,
    ContextBudgeter,
    BudgetAllocation,
    get_model_limit,
    get_output_reserve,
)


def agent_centric_example():
    """Agent-centric usage - recommended approach."""
    print("=" * 60)
    print("Agent-Centric Context Budgeting")
    print("=" * 60)
    
    # Simple: Enable context management with defaults
    agent = Agent(
        instructions="You are a helpful assistant.",
        context=True,
    )
    print(f"Agent with context=True created")
    print(f"Context manager: {agent.context_manager is not None}")
    
    # Custom: Specify output reserve
    agent2 = Agent(
        instructions="You are a code assistant.",
        context=ManagerConfig(output_reserve=16000),
    )
    print(f"Agent with custom output_reserve created")
    if agent2.context_manager:
        stats = agent2.context_manager.get_stats()
        print(f"Output reserve: {stats.get('output_reserve', 'N/A')}")


def main():
    print("=" * 60)
    print("Context Budgeting Example")
    print("=" * 60)
    
    # Example 1: Basic budget allocation for GPT-4o-mini
    print("\n1. Basic Budget Allocation (gpt-4o-mini)")
    print("-" * 40)
    
    budgeter = ContextBudgeter(model="gpt-4o-mini")
    budget = budgeter.allocate()
    
    print(f"Model: gpt-4o-mini")
    print(f"Model Limit: {budget.model_limit:,} tokens")
    print(f"Output Reserve: {budget.output_reserve:,} tokens")
    print(f"Usable Context: {budget.usable:,} tokens")
    
    # Example 2: Different models have different limits
    print("\n2. Model Comparison")
    print("-" * 40)
    
    models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "claude-3-opus", "gemini-1.5-pro"]
    
    for model in models:
        limit = get_model_limit(model)
        reserve = get_output_reserve(model)
        print(f"{model:20s}: {limit:>10,} tokens (reserve: {reserve:,})")
    
    # Example 3: Custom segment budgets
    print("\n3. Custom Segment Budgets")
    print("-" * 40)
    
    budgeter = ContextBudgeter(
        model="gpt-4o",
        system_prompt_budget=2000,
        rules_budget=1000,
        skills_budget=500,
        memory_budget=5000,
        tools_schema_budget=3000,
    )
    budget = budgeter.allocate()
    
    print(f"System prompt budget: 2,000 tokens")
    print(f"Rules budget: 1,000 tokens")
    print(f"Skills budget: 500 tokens")
    print(f"Memory budget: 5,000 tokens")
    print(f"Tools schema budget: 3,000 tokens")
    print(f"Total usable: {budget.usable:,} tokens")
    
    # Example 4: Check for overflow
    print("\n4. Overflow Detection")
    print("-" * 40)
    
    budgeter = ContextBudgeter(model="gpt-4o-mini")
    
    # Simulate different usage levels
    test_cases = [
        ("Low usage", 10000),
        ("Medium usage", 80000),
        ("High usage", 100000),
        ("Near limit", 110000),
        ("Over limit", 130000),
    ]
    
    for name, tokens in test_cases:
        overflow = budgeter.check_overflow(tokens)
        utilization = budgeter.get_utilization(tokens)
        remaining = budgeter.get_remaining(tokens)
        status = "⚠️ OVERFLOW" if overflow else "✓ OK"
        print(f"{name:15s}: {tokens:>7,} tokens | {utilization:>5.1%} | {status}")
    
    # Example 5: Budget to dict for serialization
    print("\n5. Budget Serialization")
    print("-" * 40)
    
    budget_dict = budgeter.to_dict()
    print(f"Budget as dict: {budget_dict}")
    
    print("\n" + "=" * 60)
    print("✓ Context budgeting examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
