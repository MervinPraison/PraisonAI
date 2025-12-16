"""
Fast Context Usage Examples.

This file demonstrates how to use the Fast Context feature for rapid code search.

Fast Context is inspired by Windsurf's SWE-grep approach:
- Parallel tool execution (up to 8 concurrent calls)
- Limited turns (max 4) for fast response
- Lightweight model for search operations
- Result caching for repeated queries
"""

# Example 1: Basic FastContext Usage
# ==================================

def example_basic_search():
    """Basic search using FastContext."""
    from praisonaiagents.context.fast import FastContext
    
    # Create FastContext instance
    fc = FastContext(workspace_path=".")
    
    # Search for a pattern
    result = fc.search("def authenticate")
    
    print(f"Found {result.total_files} files")
    print(f"Search time: {result.search_time_ms}ms")
    
    # Print results
    for file_match in result.files[:5]:
        print(f"  - {file_match.path}")
        for lr in file_match.line_ranges:
            print(f"    Lines {lr.start}-{lr.end}")


# Example 2: Search with Patterns
# ===============================

def example_search_with_patterns():
    """Search with include/exclude patterns."""
    from praisonaiagents.context.fast import FastContext
    
    fc = FastContext(workspace_path=".")
    
    # Search only in Python files
    result = fc.search(
        "class Agent",
        include_patterns=["**/*.py"],
        exclude_patterns=["**/tests/**", "**/test_*.py"]
    )
    
    print(f"Found {result.total_files} files matching 'class Agent'")
    for f in result.files:
        print(f"  - {f.path}")


# Example 3: Get Context for Agent
# ================================

def example_get_context_for_agent():
    """Get formatted context string for an agent."""
    from praisonaiagents.context.fast import FastContext
    
    fc = FastContext(workspace_path=".")
    
    # Get context formatted for injection into an agent
    context = fc.get_context_for_agent(
        "authentication handlers",
        max_files=5,
        max_lines_per_file=50
    )
    
    print("Context for agent:")
    print(context[:500] + "..." if len(context) > 500 else context)


# Example 4: Agent with FastContext Integration
# =============================================

def example_agent_with_fast_context():
    """Use FastContext with an Agent."""
    from praisonaiagents import Agent
    
    # Create agent with FastContext enabled
    agent = Agent(
        name="CodeAssistant",
        instructions="You are a helpful code assistant.",
        fast_context=True,
        fast_context_path=".",  # Current directory
        fast_context_model="gpt-4o-mini",
        fast_context_max_turns=4,
        fast_context_parallelism=8
    )
    
    # Use delegate_to_fast_context for code search
    context = agent.delegate_to_fast_context("find authentication code")
    
    if context:
        print("Found relevant code context:")
        print(context[:300] + "...")
    else:
        print("No relevant code found")


# Example 5: File Indexer
# =======================

def example_file_indexer():
    """Use FileIndexer for fast file lookups."""
    from praisonaiagents.context.fast.indexer import FileIndexer
    
    # Create and run indexer
    indexer = FileIndexer(workspace_path=".")
    count = indexer.index()
    
    print(f"Indexed {count} files")
    
    # Find files by pattern
    py_files = indexer.find_by_pattern("**/*.py")
    print(f"Found {len(py_files)} Python files")
    
    # Find files by extension
    js_files = indexer.find_by_extension(".js")
    print(f"Found {len(js_files)} JavaScript files")
    
    # Get stats
    stats = indexer.get_stats()
    print(f"Total size: {stats['total_size_mb']} MB")


# Example 6: Symbol Indexer
# =========================

def example_symbol_indexer():
    """Use SymbolIndexer to find code symbols."""
    from praisonaiagents.context.fast.indexer import SymbolIndexer, SymbolType
    
    # Create and run indexer
    indexer = SymbolIndexer(workspace_path=".")
    count = indexer.index()
    
    print(f"Indexed {count} symbols")
    
    # Find symbols by name
    agent_symbols = indexer.find_by_name("Agent")
    print(f"Found {len(agent_symbols)} symbols containing 'Agent'")
    
    # Find all classes
    classes = indexer.find_by_type(SymbolType.CLASS)
    print(f"Found {len(classes)} classes")
    
    # Get stats
    stats = indexer.get_stats()
    print(f"Symbols by type: {stats['by_type']}")


# Example 7: Context Injector
# ===========================

def example_context_injector():
    """Use ContextInjector to format results for agents."""
    from praisonaiagents.context.fast import FastContext
    from praisonaiagents.context.fast.context_injector import (
        ContextInjector,
        InjectionConfig
    )
    
    # Search for code
    fc = FastContext(workspace_path=".")
    result = fc.search("def main")
    
    # Configure injection
    config = InjectionConfig(
        max_tokens=2000,
        max_files=5,
        format_style="markdown",  # or "xml", "plain"
        prioritize_precision=True
    )
    
    # Inject into prompts
    injector = ContextInjector(config)
    formatted = injector.format_context(result)
    
    print("Formatted context:")
    print(formatted[:500] + "..." if len(formatted) > 500 else formatted)


# Example 8: Environment Variable Configuration
# =============================================

def example_env_config():
    """Configure FastContext via environment variables."""
    import os
    
    # Set environment variables (usually done in shell or .env file)
    os.environ["FAST_CONTEXT_MODEL"] = "gpt-4o-mini"
    os.environ["FAST_CONTEXT_MAX_TURNS"] = "4"
    os.environ["FAST_CONTEXT_PARALLELISM"] = "8"
    os.environ["FAST_CONTEXT_TIMEOUT"] = "30.0"
    os.environ["FAST_CONTEXT_CACHE"] = "true"
    os.environ["FAST_CONTEXT_CACHE_TTL"] = "300"
    
    from praisonaiagents.context.fast import FastContext
    
    # FastContext will use environment variables as defaults
    fc = FastContext(workspace_path=".")
    
    print(f"Model: {fc.model}")
    print(f"Max turns: {fc.max_turns}")
    print(f"Max parallel: {fc.max_parallel}")
    print(f"Cache enabled: {fc.cache_enabled}")


# Example 9: Caching
# ==================

def example_caching():
    """Demonstrate result caching."""
    from praisonaiagents.context.fast import FastContext
    
    fc = FastContext(
        workspace_path=".",
        cache_enabled=True,
        cache_ttl=300  # 5 minutes
    )
    
    # First search - not cached
    result1 = fc.search("def main")
    print(f"First search: from_cache={result1.from_cache}, time={result1.search_time_ms}ms")
    
    # Second search - cached
    result2 = fc.search("def main")
    print(f"Second search: from_cache={result2.from_cache}, time={result2.search_time_ms}ms")
    
    # Clear cache
    fc.clear_cache()
    
    # Third search - not cached
    result3 = fc.search("def main")
    print(f"Third search: from_cache={result3.from_cache}, time={result3.search_time_ms}ms")


# Example 10: Context Manager
# ===========================

def example_context_manager():
    """Use FastContext as a context manager."""
    from praisonaiagents.context.fast import FastContext
    
    with FastContext(workspace_path=".") as fc:
        result = fc.search("import")
        print(f"Found {result.total_files} files with imports")
    
    # Resources are automatically cleaned up


if __name__ == "__main__":
    print("=" * 60)
    print("Fast Context Examples")
    print("=" * 60)
    
    print("\n1. Basic Search")
    print("-" * 40)
    example_basic_search()
    
    print("\n2. Search with Patterns")
    print("-" * 40)
    example_search_with_patterns()
    
    print("\n3. Get Context for Agent")
    print("-" * 40)
    example_get_context_for_agent()
    
    print("\n5. File Indexer")
    print("-" * 40)
    example_file_indexer()
    
    print("\n9. Caching")
    print("-" * 40)
    example_caching()
    
    print("\n10. Context Manager")
    print("-" * 40)
    example_context_manager()
    
    print("\n" + "=" * 60)
    print("All examples completed!")
