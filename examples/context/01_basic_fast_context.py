"""
Example 1: Basic Fast Context Usage

This example demonstrates the basic usage of Fast Context for rapid code search.
Fast Context is 10-20x faster than traditional sequential search because it:
- Executes up to 8 tool calls in parallel
- Limits search to 4 turns maximum
- Uses a lightweight model optimized for search
"""

from praisonaiagents.context.fast import FastContext
import time

def main():
    print("=" * 70)
    print("Fast Context - Basic Usage Example")
    print("=" * 70)
    
    # Create FastContext instance pointing to the praisonai-agents codebase
    fc = FastContext(
        workspace_path="/Users/praison/praisonai-package/src/praisonai-agents"
    )
    
    # Example 1: Simple pattern search
    print("\n1. Simple Pattern Search")
    print("-" * 40)
    
    start = time.perf_counter()
    result = fc.search("def chat")
    elapsed = (time.perf_counter() - start) * 1000
    
    print(f"   Query: 'def chat'")
    print(f"   Files found: {result.total_files}")
    print(f"   Search time: {result.search_time_ms}ms (total: {elapsed:.0f}ms)")
    print(f"   Turns used: {result.turns_used}")
    print(f"   Tool calls: {result.total_tool_calls}")
    
    if result.files:
        print("\n   Top matches:")
        for f in result.files[:3]:
            print(f"   - {f.path}")
            for lr in f.line_ranges[:2]:
                print(f"     Lines {lr.start}-{lr.end}")
    
    # Example 2: Search for class definitions
    print("\n2. Search for Class Definitions")
    print("-" * 40)
    
    result = fc.search("class Agent")
    print(f"   Query: 'class Agent'")
    print(f"   Files found: {result.total_files}")
    print(f"   Search time: {result.search_time_ms}ms")
    
    if result.files:
        print("\n   Files containing 'class Agent':")
        for f in result.files[:5]:
            print(f"   - {f.path} (relevance: {f.relevance_score:.2f})")
    
    # Example 3: Search for imports
    print("\n3. Search for Specific Imports")
    print("-" * 40)
    
    result = fc.search("from typing import")
    print(f"   Query: 'from typing import'")
    print(f"   Files found: {result.total_files}")
    print(f"   Search time: {result.search_time_ms}ms")
    
    # Example 4: Get formatted context string
    print("\n4. Get Formatted Context for Agent")
    print("-" * 40)
    
    context = fc.get_context_for_agent("authentication", max_files=3)
    print(f"   Context length: {len(context)} characters")
    print(f"   Preview:")
    preview = context[:300].replace('\n', '\n   ')
    print(f"   {preview}...")
    
    print("\n" + "=" * 70)
    print("Fast Context provides rapid, parallel code search!")
    print("=" * 70)


if __name__ == "__main__":
    main()
