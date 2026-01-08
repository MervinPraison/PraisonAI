"""
Example 4: Agent Integration with Context Management

This example shows how to use context management with the Agent class.
Context management is now unified via the context= parameter.

Benefits:
- Seamless integration with existing Agent workflows
- Automatic token tracking and optimization
- Configurable via context= parameter with ManagerConfig
"""

from praisonaiagents import Agent
from praisonaiagents.context import ManagerConfig

WORKSPACE = "/Users/praison/praisonai-package/src/praisonai-agents"


def main():
    print("=" * 70)
    print("Agent Integration with Context Management")
    print("=" * 70)
    
    # Create an agent with context management enabled
    print("\n1. Creating Agent with Context Management")
    print("-" * 40)
    
    config = ManagerConfig(
        auto_compact=True,
        compact_threshold=0.8,
        strategy="smart",
        monitor_enabled=True,
        monitor_path="./context_debug.txt",
    )
    
    agent = Agent(
        name="CodeAssistant",
        instructions="You are a helpful code assistant.",
        context=config,
        verbose=False
    )
    
    print(f"   Agent name: {agent.name}")
    print(f"   Context manager: {agent.context_manager is not None}")
    if agent.context_manager:
        print(f"   Auto-compact: {agent.context_manager.config.auto_compact}")
        print(f"   Threshold: {agent.context_manager.config.compact_threshold}")
        print(f"   Strategy: {agent.context_manager.config.strategy}")
    
    # For FastContext code search, use the module directly
    print("\n2. Using FastContext for Code Search")
    print("-" * 40)
    
    try:
        from praisonaiagents.context.fast import FastContext
        
        fc = FastContext(
            workspace_path=WORKSPACE,
            model="gpt-4o-mini",
            max_turns=4,
            max_parallel=8,
            timeout=30.0,
        )
        
        queries = [
            "find the Agent class definition",
            "search for chat method",
        ]
        
        for query in queries:
            print(f"\n   Query: '{query}'")
            result = fc.search(query)
            print(f"   Files found: {result.total_files}")
            print(f"   Search time: {result.search_time_ms}ms")
            
    except ImportError:
        print("   FastContext not available (optional feature)")
    except Exception as e:
        print(f"   FastContext error: {e}")
    
    # Show configuration options
    print("\n3. Configuration Options")
    print("-" * 40)
    
    print("   Agent context= parameter:")
    print("   - context=True                   # Enable with defaults")
    print("   - context=ManagerConfig(...)     # Custom configuration")
    print("   - context=False                  # Disabled (default)")
    
    print("\n   ManagerConfig options:")
    print("   - auto_compact=True              # Auto-optimize context")
    print("   - compact_threshold=0.8          # Trigger at 80%")
    print("   - strategy='smart'               # Optimization strategy")
    print("   - monitor_enabled=True           # Write snapshots")
    print("   - monitor_path='./context.txt'   # Snapshot path")
    print("   - FAST_CONTEXT_PARALLELISM")
    print("   - FAST_CONTEXT_TIMEOUT")
    print("   - FAST_CONTEXT_CACHE")
    print("   - FAST_CONTEXT_CACHE_TTL")
    
    print("\n" + "=" * 70)
    print("Fast Context integrates seamlessly with Agent for code search!")
    print("=" * 70)


if __name__ == "__main__":
    main()
