#!/usr/bin/env python3
"""
Basic Context Compaction Example for PraisonAI Agents.

This example demonstrates how to use context compaction with Agent:
1. Create an Agent with context= parameter for compaction
2. Use different compaction strategies via ManagerConfig
3. Monitor compaction results

Usage:
    python basic_compaction.py
"""

from praisonaiagents import Agent
from praisonaiagents.context import ManagerConfig


def main():
    print("=" * 60)
    print("Agent-Centric Context Compaction Demo")
    print("=" * 60)
    
    # ==========================================================================
    # Available Strategies
    # ==========================================================================
    print("\n--- Available Compaction Strategies ---")
    
    strategies = [
        ("truncate", "Remove oldest messages first"),
        ("sliding_window", "Keep most recent messages within limit"),
        ("summarize", "Replace old messages with summary"),
        ("smart", "Intelligently select messages to keep"),
    ]
    
    for name, desc in strategies:
        print(f"  {name}: {desc}")
    
    # ==========================================================================
    # Agent with Context Compaction via context= param
    # ==========================================================================
    print("\n--- Creating Agent with Context Compaction ---")
    
    # Use context= parameter with ManagerConfig for compaction
    agent = Agent(
        name="LongChat",
        instructions="You are a helpful assistant for extended conversations.",
        context=ManagerConfig(
            auto_compact=True,
            compact_threshold=0.8,
            strategy="sliding_window",
        )
    )
    
    print(f"Agent: {agent.name}")
    print(f"Context manager: {agent.context_manager is not None}")
    if agent.context_manager:
        print(f"Auto-compact: {agent.context_manager.config.auto_compact}")
        print(f"Threshold: {agent.context_manager.config.compact_threshold}")
        print(f"Strategy: {agent.context_manager.config.strategy}")
    
    # ==========================================================================
    # Different Strategy Examples via context= param
    # ==========================================================================
    print("\n--- Strategy Examples ---")
    
    # Sliding window strategy
    sliding_agent = Agent(
        name="SlidingAgent",
        instructions="You are helpful.",
        context=ManagerConfig(
            auto_compact=True,
            strategy="sliding_window",
        )
    )
    print(f"  Sliding: strategy={sliding_agent.context_manager.config.strategy}")
    
    # Summarize strategy
    summarize_agent = Agent(
        name="SummarizeAgent",
        instructions="You are helpful.",
        context=ManagerConfig(
            auto_compact=True,
            strategy="summarize",
        )
    )
    print(f"  Summarize: strategy={summarize_agent.context_manager.config.strategy}")
    
    # Smart strategy
    smart_agent = Agent(
        name="SmartAgent",
        instructions="You are helpful.",
        context=ManagerConfig(
            auto_compact=True,
            strategy="smart",
        )
    )
    print(f"  Smart: strategy={smart_agent.context_manager.config.strategy}")
    
    # ==========================================================================
    # Context Manager Stats Demo
    # ==========================================================================
    print("\n--- Context Manager Stats Demo ---")
    
    # Access context manager stats
    if agent.context_manager:
        stats = agent.context_manager.get_stats()
        print(f"  Model: {stats.get('model', 'N/A')}")
        print(f"  Model limit: {stats.get('model_limit', 'N/A')}")
        print(f"  Output reserve: {stats.get('output_reserve', 'N/A')}")
        print(f"  Usable budget: {stats.get('usable_budget', 'N/A')}")
    else:
        print("  Context manager not initialized")
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
