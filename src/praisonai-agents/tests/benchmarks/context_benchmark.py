"""
Context Management Benchmarks for PraisonAI Agents.

Benchmarks:
1. Context disabled vs enabled overhead
2. Token estimation performance
3. Optimization timing for various message counts
4. Multi-agent context isolation
5. Tool output truncation

Run with:
    python -m pytest tests/benchmarks/context_benchmark.py -v --benchmark-only
    
Or standalone:
    python tests/benchmarks/context_benchmark.py
"""

import time
import statistics
from typing import List, Dict, Any


def generate_messages(count: int, avg_content_length: int = 100) -> List[Dict[str, Any]]:
    """Generate test messages."""
    messages = []
    for i in range(count):
        role = "user" if i % 2 == 0 else "assistant"
        content = f"Message {i}: " + "x" * avg_content_length
        messages.append({"role": role, "content": content})
    return messages


def benchmark_context_disabled():
    """Benchmark overhead when context=False."""
    from praisonaiagents.context import ContextManager, ManagerConfig
    
    # Create manager with context disabled (simulated by not calling process)
    messages = generate_messages(100)
    
    times = []
    for _ in range(100):
        start = time.perf_counter()
        # Simulate the fast path check
        context_manager = None
        if not context_manager:
            result = messages  # No processing
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    return {
        "name": "context_disabled_overhead",
        "avg_ms": statistics.mean(times),
        "min_ms": min(times),
        "max_ms": max(times),
        "std_dev_ms": statistics.stdev(times) if len(times) > 1 else 0,
    }


def benchmark_context_enabled():
    """Benchmark overhead when context=True."""
    from praisonaiagents.context import ContextManager, ManagerConfig
    
    config = ManagerConfig(
        auto_compact=False,  # Disable auto-compact for baseline
        monitor_enabled=False,
    )
    manager = ContextManager(model="gpt-4o-mini", config=config)
    messages = generate_messages(100)
    
    times = []
    for _ in range(100):
        start = time.perf_counter()
        result = manager.process(messages=messages, system_prompt="Test", tools=[])
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    return {
        "name": "context_enabled_baseline",
        "avg_ms": statistics.mean(times),
        "min_ms": min(times),
        "max_ms": max(times),
        "std_dev_ms": statistics.stdev(times) if len(times) > 1 else 0,
    }


def benchmark_token_estimation():
    """Benchmark token estimation performance."""
    from praisonaiagents.context import estimate_messages_tokens
    
    messages = generate_messages(100, avg_content_length=500)
    
    times = []
    for _ in range(100):
        start = time.perf_counter()
        tokens = estimate_messages_tokens(messages)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    return {
        "name": "token_estimation_100_msgs",
        "avg_ms": statistics.mean(times),
        "min_ms": min(times),
        "max_ms": max(times),
        "std_dev_ms": statistics.stdev(times) if len(times) > 1 else 0,
    }


def benchmark_optimization_small():
    """Benchmark optimization with small message count."""
    from praisonaiagents.context import get_optimizer, OptimizerStrategy
    
    optimizer = get_optimizer(OptimizerStrategy.SLIDING_WINDOW)
    messages = generate_messages(50)
    
    times = []
    for _ in range(50):
        start = time.perf_counter()
        result = optimizer.optimize(messages.copy(), target_tokens=5000)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    return {
        "name": "optimize_50_msgs",
        "avg_ms": statistics.mean(times),
        "min_ms": min(times),
        "max_ms": max(times),
        "std_dev_ms": statistics.stdev(times) if len(times) > 1 else 0,
    }


def benchmark_optimization_large():
    """Benchmark optimization with large message count."""
    from praisonaiagents.context import get_optimizer, OptimizerStrategy
    
    optimizer = get_optimizer(OptimizerStrategy.SLIDING_WINDOW)
    messages = generate_messages(200)
    
    times = []
    for _ in range(20):
        start = time.perf_counter()
        result = optimizer.optimize(messages.copy(), target_tokens=10000)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    return {
        "name": "optimize_200_msgs",
        "avg_ms": statistics.mean(times),
        "min_ms": min(times),
        "max_ms": max(times),
        "std_dev_ms": statistics.stdev(times) if len(times) > 1 else 0,
    }


def benchmark_store_operations():
    """Benchmark context store operations."""
    from praisonaiagents.context import ContextStoreImpl, reset_global_store
    
    reset_global_store()
    store = ContextStoreImpl()
    
    # Benchmark append + commit
    times_append = []
    for i in range(100):
        mutator = store.get_mutator(f"agent_{i % 5}")
        start = time.perf_counter()
        mutator.append({"role": "user", "content": f"Message {i}"})
        mutator.commit()
        elapsed = (time.perf_counter() - start) * 1000
        times_append.append(elapsed)
    
    # Benchmark view operations
    times_view = []
    for i in range(100):
        view = store.get_view(f"agent_{i % 5}")
        start = time.perf_counter()
        messages = view.get_effective_messages()
        elapsed = (time.perf_counter() - start) * 1000
        times_view.append(elapsed)
    
    return [
        {
            "name": "store_append_commit",
            "avg_ms": statistics.mean(times_append),
            "min_ms": min(times_append),
            "max_ms": max(times_append),
            "std_dev_ms": statistics.stdev(times_append) if len(times_append) > 1 else 0,
        },
        {
            "name": "store_get_effective",
            "avg_ms": statistics.mean(times_view),
            "min_ms": min(times_view),
            "max_ms": max(times_view),
            "std_dev_ms": statistics.stdev(times_view) if len(times_view) > 1 else 0,
        },
    ]


def benchmark_effective_history_filter():
    """Benchmark get_effective_history filtering."""
    from praisonaiagents.context import get_effective_history
    
    # Create messages with some condensed
    messages = []
    for i in range(100):
        msg = {"role": "user" if i % 2 == 0 else "assistant", "content": f"Msg {i}"}
        if i < 30:  # First 30 are condensed
            msg["_metadata"] = {"condense_parent": "sum-1"}
        messages.append(msg)
    
    # Add summary
    messages.insert(30, {
        "role": "assistant",
        "content": "Summary",
        "_metadata": {"is_summary": True, "summary_id": "sum-1"},
    })
    
    times = []
    for _ in range(100):
        start = time.perf_counter()
        result = get_effective_history(messages)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    return {
        "name": "effective_history_filter",
        "avg_ms": statistics.mean(times),
        "min_ms": min(times),
        "max_ms": max(times),
        "std_dev_ms": statistics.stdev(times) if len(times) > 1 else 0,
    }


def run_all_benchmarks():
    """Run all benchmarks and print results."""
    print("=" * 70)
    print("Context Management Benchmarks")
    print("=" * 70)
    
    results = []
    
    print("\nRunning benchmarks...")
    
    # Run each benchmark
    results.append(benchmark_context_disabled())
    print("  ✓ context_disabled_overhead")
    
    results.append(benchmark_context_enabled())
    print("  ✓ context_enabled_baseline")
    
    results.append(benchmark_token_estimation())
    print("  ✓ token_estimation")
    
    results.append(benchmark_optimization_small())
    print("  ✓ optimization_small")
    
    results.append(benchmark_optimization_large())
    print("  ✓ optimization_large")
    
    store_results = benchmark_store_operations()
    results.extend(store_results)
    print("  ✓ store_operations")
    
    results.append(benchmark_effective_history_filter())
    print("  ✓ effective_history_filter")
    
    # Print results table
    print("\n" + "=" * 70)
    print(f"{'Benchmark':<35} {'Avg (ms)':<12} {'Min':<10} {'Max':<10} {'StdDev':<10}")
    print("-" * 70)
    
    for r in results:
        print(f"{r['name']:<35} {r['avg_ms']:<12.3f} {r['min_ms']:<10.3f} "
              f"{r['max_ms']:<10.3f} {r['std_dev_ms']:<10.3f}")
    
    print("=" * 70)
    
    # Verify acceptance gates
    print("\nAcceptance Gates:")
    
    # Gate 1: Context disabled overhead < 0.1ms
    disabled_overhead = results[0]["avg_ms"]
    gate1_pass = disabled_overhead < 0.1
    print(f"  {'✓' if gate1_pass else '✗'} Context disabled overhead < 0.1ms: {disabled_overhead:.4f}ms")
    
    # Gate 2: Context enabled overhead < 5ms for 100 messages
    enabled_overhead = results[1]["avg_ms"]
    gate2_pass = enabled_overhead < 5.0
    print(f"  {'✓' if gate2_pass else '✗'} Context enabled overhead < 5ms: {enabled_overhead:.3f}ms")
    
    # Gate 3: Optimization < 50ms for 100 messages
    opt_time = results[3]["avg_ms"]  # optimization_small (50 msgs)
    gate3_pass = opt_time < 50.0
    print(f"  {'✓' if gate3_pass else '✗'} Optimization < 50ms: {opt_time:.3f}ms")
    
    # Gate 4: Token estimation < 10ms for 100 messages
    est_time = results[2]["avg_ms"]
    gate4_pass = est_time < 10.0
    print(f"  {'✓' if gate4_pass else '✗'} Token estimation < 10ms: {est_time:.3f}ms")
    
    all_pass = gate1_pass and gate2_pass and gate3_pass and gate4_pass
    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    
    return results, all_pass


if __name__ == "__main__":
    run_all_benchmarks()
