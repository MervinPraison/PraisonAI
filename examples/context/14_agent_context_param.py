#!/usr/bin/env python3
"""
Agent-Centric Context Management Example

Demonstrates the recommended way to use context management with the new
`context=` parameter. This is the simplest and most powerful approach.

The `context=` parameter accepts:
- False (default): Zero overhead, no context management
- True: Enable with safe defaults (auto-compact, smart strategy)
- ManagerConfig: Custom configuration object
- ContextManager: Pre-configured manager instance

Requires: OPENAI_API_KEY environment variable
"""

import os
from praisonaiagents import Agent
from praisonaiagents.context import ManagerConfig


def example_1_simple_enable():
    """Simplest usage - just enable context management."""
    print("=" * 60)
    print("Example 1: Simple Enable (context=True)")
    print("=" * 60)
    
    # Create agent with context management enabled
    agent = Agent(
        instructions="You are a helpful assistant. Keep responses concise.",
        llm="gpt-4o-mini",
        context=True,  # Enable with safe defaults
    )
    
    # The agent now automatically:
    # - Tracks token usage
    # - Optimizes when approaching limits (80% threshold)
    # - Uses smart optimization strategy
    
    print("Agent created with context management enabled")
    print(f"Context manager initialized: {agent.context_manager is not None}")
    
    if agent.context_manager:
        print(f"Model: {agent.context_manager.model}")
        print(f"Auto-compact: {agent.context_manager.config.auto_compact}")
        print(f"Threshold: {agent.context_manager.config.compact_threshold}")
        print(f"Strategy: {agent.context_manager.config.strategy}")
    
    # Make a chat call
    if os.environ.get("OPENAI_API_KEY"):
        response = agent.chat("What is 2+2?")
        print(f"\nResponse: {response}")
    else:
        print("\nSkipping API call (no OPENAI_API_KEY)")
    
    print()


def example_2_custom_config():
    """Custom configuration with ManagerConfig."""
    print("=" * 60)
    print("Example 2: Custom Configuration (context=ManagerConfig)")
    print("=" * 60)
    
    # Create custom configuration
    config = ManagerConfig(
        auto_compact=True,
        compact_threshold=0.7,  # Trigger at 70% instead of 80%
        strategy="smart",
        monitor_enabled=True,
        monitor_path="./context_debug.txt",
        monitor_format="human",
        redact_sensitive=True,
        output_reserve=8000,
    )
    
    # Create agent with custom config
    agent = Agent(
        instructions="You are a code assistant.",
        llm="gpt-4o-mini",
        context=config,
    )
    
    print("Agent created with custom context config")
    print(f"Threshold: {agent.context_manager.config.compact_threshold}")
    print(f"Monitor enabled: {agent.context_manager.config.monitor_enabled}")
    print(f"Monitor path: {agent.context_manager.config.monitor_path}")
    
    if os.environ.get("OPENAI_API_KEY"):
        response = agent.chat("Write a hello world in Python")
        print(f"\nResponse: {response[:200]}...")
    else:
        print("\nSkipping API call (no OPENAI_API_KEY)")
    
    print()


def example_3_disabled():
    """Disabled context management - zero overhead."""
    print("=" * 60)
    print("Example 3: Disabled (context=False)")
    print("=" * 60)
    
    # Create agent without context management (default)
    agent = Agent(
        instructions="You are a simple assistant.",
        llm="gpt-4o-mini",
        context=False,  # Explicit disable (same as default)
    )
    
    print("Agent created without context management")
    print(f"Context manager: {agent.context_manager}")
    print("Zero overhead: No token tracking, no optimization")
    
    if os.environ.get("OPENAI_API_KEY"):
        response = agent.chat("Hello!")
        print(f"\nResponse: {response}")
    else:
        print("\nSkipping API call (no OPENAI_API_KEY)")
    
    print()


def example_4_access_stats():
    """Access context statistics and history."""
    print("=" * 60)
    print("Example 4: Access Context Stats")
    print("=" * 60)
    
    agent = Agent(
        instructions="You are helpful.",
        llm="gpt-4o-mini",
        context=True,
    )
    
    manager = agent.context_manager
    
    # Access budget info via internal attribute
    budget = manager._budget
    print(f"Model limit: {budget.model_limit:,} tokens")
    print(f"Output reserve: {budget.output_reserve:,} tokens")
    print(f"Usable budget: {budget.usable:,} tokens")
    
    # Access config
    print("\nConfiguration:")
    print(f"  Auto-compact: {manager.config.auto_compact}")
    print(f"  Threshold: {manager.config.compact_threshold}")
    print(f"  Strategy: {manager.config.strategy}")
    
    print()


def example_5_multi_agent():
    """Multi-agent with shared context management."""
    print("=" * 60)
    print("Example 5: Multi-Agent Context Management")
    print("=" * 60)
    
    from praisonaiagents import AgentManager, Task
    
    config = ManagerConfig(
        auto_compact=True,
        compact_threshold=0.8,
    )
    
    # Create agents
    researcher = Agent(
        name="Researcher",
        instructions="You research topics thoroughly.",
        llm="gpt-4o-mini",
    )
    
    writer = Agent(
        name="Writer", 
        instructions="You write clear summaries.",
        llm="gpt-4o-mini",
    )
    
    # Create tasks
    task1 = Task(description="Research AI trends", agent=researcher)
    task2 = Task(description="Write a summary", agent=writer)
    
    # Create multi-agent system with context management
    agents = AgentManager(
        agents=[researcher, writer],
        tasks=[task1, task2],
        context=config,  # Shared context config
    )
    
    print("Multi-agent system created")
    print(f"Context manager: {agents.context_manager is not None}")
    
    if agents.context_manager:
        print("Type: MultiAgentContextManager")
        print("Provides per-agent isolation with shared config")
    
    print()


def main():
    print("\n" + "=" * 60)
    print("Agent-Centric Context Management Examples")
    print("=" * 60 + "\n")
    
    example_1_simple_enable()
    example_2_custom_config()
    example_3_disabled()
    example_4_access_stats()
    example_5_multi_agent()
    
    print("=" * 60)
    print("✓ All examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
