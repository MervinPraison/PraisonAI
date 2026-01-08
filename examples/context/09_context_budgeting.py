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
    
    # Example 6: Overflow handling strategies overview
    print("\n6. Overflow Handling Strategies")
    print("-" * 40)
    strategies = [
        ("truncate", "Remove oldest messages first", "Fast, simple", "Loses early context"),
        ("sliding_window", "Keep N most recent messages", "Preserves recent", "Loses early context"),
        ("prune_tools", "Truncate old tool outputs", "Keeps messages", "May lose tool details"),
        ("summarize", "Replace old messages with summary", "Preserves meaning", "Slower, uses API"),
        ("smart", "Combine strategies intelligently", "Best balance", "More complex"),
    ]
    print(f"{'Strategy':<15} | {'Description':<30} | {'Pros':<18} | {'Cons'}")
    print("-" * 90)
    for name, desc, pros, cons in strategies:
        print(f"{name:<15} | {desc:<30} | {pros:<18} | {cons}")
    
    # Example 7: Simulated overflow playbook
    print("\n7. Overflow Playbook (Thresholds → Actions)")
    print("-" * 40)
    playbook = [
        (0.70, "INFO", "Monitor usage, no action needed"),
        (0.80, "NOTICE", "Consider optimization soon"),
        (0.90, "WARNING", "Trigger auto-compact if enabled"),
        (0.95, "CRITICAL", "Aggressive optimization required"),
        (1.00, "OVERFLOW", "Immediate truncation to prevent API error"),
    ]
    print(f"{'Usage':<8} | {'Level':<10} | {'Action'}")
    print("-" * 60)
    for threshold, level, action in playbook:
        print(f"{threshold:>6.0%}   | {level:<10} | {action}")
    
    # Example 8: Strategy comparison table
    print("\n8. Strategy Comparison")
    print("-" * 40)
    print("Strategy         | Preserves      | Loses          | Best For")
    print("-" * 70)
    print("truncate         | Recent msgs    | Old msgs       | Simple chats")
    print("sliding_window   | Last N msgs    | Earlier msgs   | Long conversations")
    print("prune_tools      | All messages   | Tool details   | Tool-heavy agents")
    print("summarize        | Context meaning| Exact wording  | Important history")
    print("smart            | Balanced       | Minimal        | Production use")
    
    # Example 9: Default strategy for interactive mode
    print("\n9. Default Strategy: Interactive Mode")
    print("-" * 40)
    print("Interactive mode default: context=False (zero overhead)")
    print("To enable context management in interactive mode:")
    print("  praisonai chat --context  # Enable with defaults")
    print("  Or in code:")
    print("    agent = Agent(instructions='...', context=True)")
    print("")
    print("When enabled, defaults are:")
    print("  - auto_compact: True")
    print("  - compact_threshold: 0.8 (80% usage)")
    print("  - strategy: smart")
    print("  - output_reserve: model-specific (8K-16K)")
    
    # Example 10: Default strategy for auto-agents mode
    print("\n10. Default Strategy: Auto-Agents Mode")
    print("-" * 40)
    print("Auto-agents mode default: context=False (zero overhead)")
    print("To enable for multi-agent workflows:")
    print("    from praisonaiagents import PraisonAIAgents")
    print("    agents = PraisonAIAgents(agents=[...], context=True)")
    print("")
    print("Recommended config for long tasks:")
    print("    context=ManagerConfig(")
    print("        auto_compact=True,")
    print("        compact_threshold=0.7,  # Earlier trigger for safety")
    print("        strategy='smart',")
    print("        output_reserve=16384,   # Larger reserve for complex outputs")
    print("    )")
    
    print("\n" + "=" * 60)
    print("✓ Context budgeting examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
