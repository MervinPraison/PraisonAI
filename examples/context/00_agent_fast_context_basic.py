"""
Fast Context with Agent - Basic Example

This is the simplest way to use Fast Context with an Agent.
Just set fast_context=True and the agent will automatically
have access to rapid code search capabilities.

Fast Context provides:
- 10-20x faster code search than traditional methods
- Parallel execution (8 concurrent searches)
- Automatic caching for repeated queries
- Seamless integration with Agent workflows
"""

from praisonaiagents import Agent

def main():
    print("=" * 60)
    print("Agent with Fast Context - Basic Example")
    print("=" * 60)
    
    # Create an agent with Fast Context enabled
    # This is the simplest configuration
    agent = Agent(
        name="CodeAssistant",
        instructions="You are a helpful code assistant.",
        fast_context=True,  # Enable Fast Context
        fast_context_path=".",  # Search in current directory
        verbose=False
    )
    
    print("\n✓ Agent created with Fast Context enabled")
    print(f"  - fast_context_enabled: {agent.fast_context_enabled}")
    print(f"  - fast_context_path: {agent.fast_context_path}")
    print(f"  - fast_context_model: {agent.fast_context_model}")
    
    # Use delegate_to_fast_context to search code
    print("\n" + "-" * 60)
    print("Searching for 'class Agent' in the codebase...")
    print("-" * 60)
    
    context = agent.delegate_to_fast_context("class Agent")
    
    if context:
        print(f"\n✓ Found relevant code!")
        print(f"  Context length: {len(context)} characters")
        print("\nPreview of found context:")
        print("-" * 40)
        # Show first 500 characters
        preview = context[:500]
        print(preview)
        if len(context) > 500:
            print("...")
    else:
        print("\n✗ No relevant code found")
    
    # Another search example
    print("\n" + "-" * 60)
    print("Searching for 'def chat' in the codebase...")
    print("-" * 60)
    
    context = agent.delegate_to_fast_context("def chat")
    
    if context:
        print(f"\n✓ Found relevant code!")
        print(f"  Context length: {len(context)} characters")
    else:
        print("\n✗ No relevant code found")
    
    # Access FastContext directly for more control
    print("\n" + "-" * 60)
    print("Direct FastContext access for advanced usage...")
    print("-" * 60)
    
    fc = agent.fast_context
    if fc:
        result = fc.search("import")
        print(f"\n✓ Direct search for 'import':")
        print(f"  Files found: {result.total_files}")
        print(f"  Search time: {result.search_time_ms}ms")
        print(f"  From cache: {result.from_cache}")
    
    print("\n" + "=" * 60)
    print("Fast Context makes code search instant for your agents!")
    print("=" * 60)


if __name__ == "__main__":
    main()
