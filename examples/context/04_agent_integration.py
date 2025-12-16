"""
Example 4: Agent Integration with Fast Context

This example shows how to use Fast Context integrated with the Agent class
for automatic code search delegation.

Benefits:
- Seamless integration with existing Agent workflows
- Automatic context injection for code-related queries
- Configurable via Agent parameters or environment variables
"""

from praisonaiagents import Agent

WORKSPACE = "/Users/praison/praisonai-package/src/praisonai-agents"


def main():
    print("=" * 70)
    print("Agent Integration with Fast Context")
    print("=" * 70)
    
    # Create an agent with Fast Context enabled
    print("\n1. Creating Agent with Fast Context")
    print("-" * 40)
    
    agent = Agent(
        name="CodeAssistant",
        instructions="You are a helpful code assistant that can search and analyze code.",
        fast_context=True,
        fast_context_path=WORKSPACE,
        fast_context_model="gpt-4o-mini",
        fast_context_max_turns=4,
        fast_context_parallelism=8,
        fast_context_timeout=30.0,
        verbose=False
    )
    
    print(f"   Agent name: {agent.name}")
    print(f"   Fast Context enabled: {agent.fast_context_enabled}")
    print(f"   Fast Context path: {agent.fast_context_path}")
    print(f"   Fast Context model: {agent.fast_context_model}")
    print(f"   Max turns: {agent.fast_context_max_turns}")
    print(f"   Parallelism: {agent.fast_context_parallelism}")
    
    # Use delegate_to_fast_context for code search
    print("\n2. Delegating Code Search to Fast Context")
    print("-" * 40)
    
    queries = [
        "find the Agent class definition",
        "search for authentication handlers",
        "locate memory management code",
    ]
    
    for query in queries:
        print(f"\n   Query: '{query}'")
        context = agent.delegate_to_fast_context(query)
        
        if context:
            # Show preview of context
            lines = context.split('\n')
            preview_lines = lines[:5]
            print(f"   Found context ({len(context)} chars):")
            for line in preview_lines:
                print(f"      {line[:60]}{'...' if len(line) > 60 else ''}")
            if len(lines) > 5:
                print(f"      ... and {len(lines) - 5} more lines")
        else:
            print("   No relevant code found")
    
    # Access the FastContext instance directly
    print("\n3. Direct FastContext Access")
    print("-" * 40)
    
    fc = agent.fast_context
    if fc:
        result = fc.search("def chat")
        print(f"   Direct search for 'def chat':")
        print(f"   Files found: {result.total_files}")
        print(f"   Search time: {result.search_time_ms}ms")
        
        for f in result.files[:3]:
            print(f"   - {f.path}")
    
    # Show configuration options
    print("\n4. Configuration Options")
    print("-" * 40)
    
    print("   Agent parameters:")
    print("   - fast_context=True              # Enable Fast Context")
    print("   - fast_context_path='.'          # Workspace path")
    print("   - fast_context_model='gpt-4o-mini'  # Search model")
    print("   - fast_context_max_turns=4       # Max search turns")
    print("   - fast_context_parallelism=8     # Parallel calls")
    print("   - fast_context_timeout=30.0      # Timeout (seconds)")
    
    print("\n   Environment variables:")
    print("   - FAST_CONTEXT_MODEL")
    print("   - FAST_CONTEXT_MAX_TURNS")
    print("   - FAST_CONTEXT_PARALLELISM")
    print("   - FAST_CONTEXT_TIMEOUT")
    print("   - FAST_CONTEXT_CACHE")
    print("   - FAST_CONTEXT_CACHE_TTL")
    
    print("\n" + "=" * 70)
    print("Fast Context integrates seamlessly with Agent for code search!")
    print("=" * 70)


if __name__ == "__main__":
    main()
