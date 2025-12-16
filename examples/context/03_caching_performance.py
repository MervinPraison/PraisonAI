"""
Example 3: Caching Performance Demonstration

This example shows how Fast Context's caching dramatically improves
performance for repeated queries.

Key benefits:
- First query: Full search execution
- Subsequent queries: Instant cache hit (0ms search time)
- Configurable TTL (time-to-live)
"""

import time
from praisonaiagents.context.fast import FastContext

WORKSPACE = "/Users/praison/praisonai-package/src/praisonai-agents"


def main():
    print("=" * 70)
    print("Fast Context Caching Performance")
    print("=" * 70)
    
    # Create FastContext with caching enabled
    fc = FastContext(
        workspace_path=WORKSPACE,
        cache_enabled=True,
        cache_ttl=300  # 5 minutes
    )
    
    query = "def execute"
    
    print(f"\nQuery: '{query}'")
    print(f"Cache TTL: 300 seconds")
    
    # First search - cache miss
    print("\n1. First Search (Cache Miss)")
    print("-" * 40)
    
    start = time.perf_counter()
    result1 = fc.search(query)
    elapsed1 = (time.perf_counter() - start) * 1000
    
    print(f"   Files found: {result1.total_files}")
    print(f"   From cache: {result1.from_cache}")
    print(f"   Search time: {result1.search_time_ms}ms")
    print(f"   Total time: {elapsed1:.1f}ms")
    
    # Second search - cache hit
    print("\n2. Second Search (Cache Hit)")
    print("-" * 40)
    
    start = time.perf_counter()
    result2 = fc.search(query)
    elapsed2 = (time.perf_counter() - start) * 1000
    
    print(f"   Files found: {result2.total_files}")
    print(f"   From cache: {result2.from_cache}")
    print(f"   Search time: {result2.search_time_ms}ms")
    print(f"   Total time: {elapsed2:.1f}ms")
    
    # Third search - still cached
    print("\n3. Third Search (Still Cached)")
    print("-" * 40)
    
    start = time.perf_counter()
    result3 = fc.search(query)
    elapsed3 = (time.perf_counter() - start) * 1000
    
    print(f"   Files found: {result3.total_files}")
    print(f"   From cache: {result3.from_cache}")
    print(f"   Total time: {elapsed3:.1f}ms")
    
    # Clear cache and search again
    print("\n4. After Cache Clear")
    print("-" * 40)
    
    fc.clear_cache()
    print("   Cache cleared!")
    
    start = time.perf_counter()
    result4 = fc.search(query)
    elapsed4 = (time.perf_counter() - start) * 1000
    
    print(f"   Files found: {result4.total_files}")
    print(f"   From cache: {result4.from_cache}")
    print(f"   Search time: {result4.search_time_ms}ms")
    print(f"   Total time: {elapsed4:.1f}ms")
    
    # Performance comparison
    print("\n5. Performance Summary")
    print("-" * 40)
    
    cache_speedup = elapsed1 / elapsed2 if elapsed2 > 0 else float('inf')
    
    print(f"   First search (no cache): {elapsed1:.1f}ms")
    print(f"   Cached searches: ~{elapsed2:.1f}ms")
    print(f"   Cache speedup: {cache_speedup:.0f}x faster")
    
    # Multiple different queries
    print("\n6. Multiple Query Caching")
    print("-" * 40)
    
    queries = ["class Agent", "async def", "import os", "def __init__"]
    
    # First pass - populate cache
    print("   First pass (populating cache):")
    start = time.perf_counter()
    for q in queries:
        fc.search(q)
    first_pass = (time.perf_counter() - start) * 1000
    print(f"   Time: {first_pass:.0f}ms")
    
    # Second pass - all cached
    print("   Second pass (all cached):")
    start = time.perf_counter()
    for q in queries:
        r = fc.search(q)
        assert r.from_cache, f"Expected cache hit for '{q}'"
    second_pass = (time.perf_counter() - start) * 1000
    print(f"   Time: {second_pass:.1f}ms")
    
    multi_speedup = first_pass / second_pass if second_pass > 0 else float('inf')
    print(f"   Speedup: {multi_speedup:.0f}x faster")
    
    print("\n" + "=" * 70)
    print("Caching provides instant results for repeated queries!")
    print("=" * 70)


if __name__ == "__main__":
    main()
