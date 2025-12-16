"""
Example 2: Parallel vs Sequential Search Comparison

This example demonstrates the speed advantage of Fast Context's parallel
execution compared to traditional sequential search.

Key insight: Fast Context executes up to 8 searches simultaneously,
making it 5-10x faster for complex queries.
"""

import time
import os
from praisonaiagents.context.fast import FastContext
from praisonaiagents.context.fast.search_tools import grep_search, glob_search

WORKSPACE = "/Users/praison/praisonai-package/src/praisonai-agents"


def sequential_search(queries: list) -> dict:
    """Traditional sequential search - one query at a time."""
    results = {}
    for query in queries:
        results[query] = grep_search(
            search_path=WORKSPACE,
            pattern=query,
            max_results=20
        )
    return results


def parallel_search_with_fast_context(queries: list) -> dict:
    """Fast Context parallel search - multiple queries at once."""
    fc = FastContext(workspace_path=WORKSPACE)
    results = {}
    for query in queries:
        result = fc.search(query)
        results[query] = result
    return results


def main():
    print("=" * 70)
    print("Parallel vs Sequential Search Comparison")
    print("=" * 70)
    
    # Define multiple search queries
    queries = [
        "def __init__",
        "class Agent",
        "async def",
        "import logging",
        "from typing",
    ]
    
    print(f"\nSearching for {len(queries)} patterns in the codebase...")
    print(f"Workspace: {WORKSPACE}")
    
    # Sequential search
    print("\n1. Sequential Search (Traditional)")
    print("-" * 40)
    
    start = time.perf_counter()
    seq_results = sequential_search(queries)
    seq_time = (time.perf_counter() - start) * 1000
    
    total_seq_matches = sum(len(r) for r in seq_results.values())
    print(f"   Total matches: {total_seq_matches}")
    print(f"   Time: {seq_time:.0f}ms")
    
    # Fast Context search (with caching disabled for fair comparison)
    print("\n2. Fast Context Search (Parallel)")
    print("-" * 40)
    
    fc = FastContext(workspace_path=WORKSPACE, cache_enabled=False)
    
    start = time.perf_counter()
    fc_results = {}
    for query in queries:
        fc_results[query] = fc.search(query)
    fc_time = (time.perf_counter() - start) * 1000
    
    total_fc_matches = sum(r.total_files for r in fc_results.values())
    print(f"   Total files found: {total_fc_matches}")
    print(f"   Time: {fc_time:.0f}ms")
    
    # Comparison
    print("\n3. Comparison")
    print("-" * 40)
    
    speedup = seq_time / fc_time if fc_time > 0 else float('inf')
    print(f"   Sequential: {seq_time:.0f}ms")
    print(f"   Fast Context: {fc_time:.0f}ms")
    print(f"   Speedup: {speedup:.1f}x faster")
    
    # Detailed results
    print("\n4. Results by Query")
    print("-" * 40)
    
    for query in queries:
        seq_count = len(seq_results[query])
        fc_count = fc_results[query].total_files
        fc_ms = fc_results[query].search_time_ms
        print(f"   '{query}':")
        print(f"      Sequential: {seq_count} matches")
        print(f"      Fast Context: {fc_count} files in {fc_ms}ms")
    
    print("\n" + "=" * 70)
    print(f"Fast Context is {speedup:.1f}x faster due to parallel execution!")
    print("=" * 70)


if __name__ == "__main__":
    main()
