"""
Fast Context - Basic Example

FastContext provides rapid code search capabilities.
Use it directly from the context module for code search.

FastContext provides:
- 10-20x faster code search than traditional methods
- Parallel execution (8 concurrent searches)
- Automatic caching for repeated queries

Note: FastContext is now accessed via the context module directly,
not as Agent parameters. For context management with agents,
use Agent(context=True) or Agent(context=ManagerConfig(...)).
"""

from praisonaiagents import Agent
from praisonaiagents.context import ManagerConfig

def main():
    print("=" * 60)
    print("Agent with Context Management - Basic Example")
    print("=" * 60)
    
    # Create an agent with context management enabled
    # This is the recommended way to use context features
    agent = Agent(
        name="CodeAssistant",
        instructions="You are a helpful code assistant.",
        context=True,  # Enable context management with defaults
    )
    
    print("\n✓ Agent created with context management enabled")
    print(f"  - context_manager: {agent.context_manager is not None}")
    if agent.context_manager:
        print(f"  - auto_compact: {agent.context_manager.config.auto_compact}")
        print(f"  - strategy: {agent.context_manager.config.strategy}")
    
    # For FastContext code search, use the module directly
    print("\n" + "-" * 60)
    print("Using FastContext for code search...")
    print("-" * 60)
    
    try:
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(
            workspace_path=".",
            model="gpt-4o-mini",
            max_turns=4,
            max_parallel=8,
        )
        
        result = fc.search("class Agent")
        print(f"\n✓ Search for 'class Agent':")
        print(f"  Files found: {result.total_files}")
        print(f"  Search time: {result.search_time_ms}ms")
        
        if result.total_files > 0:
            context = fc.get_context_for_agent("class Agent")
            print(f"  Context length: {len(context)} characters")
    except ImportError:
        print("\n⚠ FastContext not available (optional feature)")
    except Exception as e:
        print(f"\n⚠ FastContext search failed: {e}")
    
    print("\n" + "=" * 60)
    print("Context management is now unified via context= param!")
    print("=" * 60)


if __name__ == "__main__":
    main()
