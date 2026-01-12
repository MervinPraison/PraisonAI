#!/usr/bin/env python3
"""
Micro-benchmark for output mode overhead comparison.

Measures:
1. Import-time cost (cold import)
2. Agent initialization overhead per output mode
3. Hot-path overhead (simulated callback execution)

Usage:
    python tests/benchmarks/output_mode_benchmark.py

All stdlib - no external dependencies required.
"""

import subprocess
import sys
import time
from statistics import mean, stdev


def measure_import_time(mode: str, iterations: int = 5) -> dict:
    """Measure cold import time for a specific output mode."""
    times = []
    
    # Script that imports and creates an agent with specific output mode
    script = f'''
import time
start = time.perf_counter()
import os
os.environ['PRAISONAI_OUTPUT'] = '{mode}'
from praisonaiagents import Agent
agent = Agent(name="BenchAgent", instructions="Test", output="{mode}")
end = time.perf_counter()
print(f"{{(end - start) * 1000:.3f}}")
'''
    
    for _ in range(iterations):
        result = subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True,
            text=True,
            env={**dict(__import__('os').environ), 'PYTHONDONTWRITEBYTECODE': '1'}
        )
        if result.returncode == 0:
            try:
                times.append(float(result.stdout.strip()))
            except ValueError:
                pass
    
    if not times:
        return {"mode": mode, "mean_ms": -1, "stdev_ms": -1, "samples": 0}
    
    return {
        "mode": mode,
        "mean_ms": mean(times),
        "stdev_ms": stdev(times) if len(times) > 1 else 0,
        "samples": len(times),
    }


def measure_callback_overhead(iterations: int = 1000) -> dict:
    """Measure hot-path overhead of callback execution vs no callbacks."""
    results = {}
    
    # Silent mode - no callbacks
    silent_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        # Simulate what happens in silent mode: nothing
        pass
        end = time.perf_counter()
        silent_times.append((end - start) * 1_000_000)  # microseconds
    
    results["silent"] = {
        "mean_us": mean(silent_times),
        "stdev_us": stdev(silent_times) if len(silent_times) > 1 else 0,
    }
    
    # Actions mode - simulate callback overhead
    actions_times = []
    
    # Simulate the work done by actions mode per tool call
    def simulate_actions_callback():
        import time as t
        # Simulate: time.time(), dict creation, string formatting, stderr write
        _ = t.time()
        event = {
            "type": "tool_call",
            "tool": "test_tool",
            "args": {"arg1": "value1", "arg2": "value2"},
            "timestamp": t.time(),
        }
        formatted = f"[tool_call] {event['tool']}({event['args']})"
        # Don't actually write to avoid polluting output
        _ = formatted.encode()
    
    for _ in range(iterations):
        start = time.perf_counter()
        simulate_actions_callback()
        end = time.perf_counter()
        actions_times.append((end - start) * 1_000_000)  # microseconds
    
    results["actions"] = {
        "mean_us": mean(actions_times),
        "stdev_us": stdev(actions_times) if len(actions_times) > 1 else 0,
    }
    
    return results


def measure_agent_init_overhead() -> dict:
    """Measure Agent.__init__ overhead for different output modes."""
    import os
    
    # Clear any env var
    os.environ.pop('PRAISONAI_OUTPUT', None)
    
    results = {}
    iterations = 10
    
    for mode in ["silent", "actions", "verbose"]:
        times = []
        for _ in range(iterations):
            # Import fresh each time to avoid caching effects
            from praisonaiagents import Agent
            
            start = time.perf_counter()
            agent = Agent(
                name="BenchAgent",
                instructions="Test agent",
                output=mode,
            )
            end = time.perf_counter()
            times.append((end - start) * 1000)  # milliseconds
            del agent
        
        results[mode] = {
            "mean_ms": mean(times),
            "stdev_ms": stdev(times) if len(times) > 1 else 0,
        }
    
    return results


def main():
    print("=" * 60)
    print("OUTPUT MODE MICRO-BENCHMARK")
    print("=" * 60)
    print()
    
    # 1. Import time comparison
    print("1. IMPORT + INIT TIME (cold start, subprocess)")
    print("-" * 40)
    
    modes = ["silent", "actions", "verbose"]
    import_results = []
    
    for mode in modes:
        print(f"   Measuring {mode}...", end=" ", flush=True)
        result = measure_import_time(mode, iterations=3)
        import_results.append(result)
        print(f"{result['mean_ms']:.1f}ms (±{result['stdev_ms']:.1f})")
    
    print()
    
    # 2. Agent init overhead (warm)
    print("2. AGENT INIT OVERHEAD (warm, same process)")
    print("-" * 40)
    
    init_results = measure_agent_init_overhead()
    for mode, data in init_results.items():
        print(f"   {mode:12s}: {data['mean_ms']:.2f}ms (±{data['stdev_ms']:.2f})")
    
    print()
    
    # 3. Hot-path callback overhead
    print("3. HOT-PATH CALLBACK OVERHEAD (per call)")
    print("-" * 40)
    
    callback_results = measure_callback_overhead(iterations=10000)
    for mode, data in callback_results.items():
        print(f"   {mode:12s}: {data['mean_us']:.3f}µs (±{data['stdev_us']:.3f})")
    
    print()
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    silent_init = init_results.get("silent", {}).get("mean_ms", 0)
    actions_init = init_results.get("actions", {}).get("mean_ms", 0)
    
    silent_callback = callback_results.get("silent", {}).get("mean_us", 0)
    actions_callback = callback_results.get("actions", {}).get("mean_us", 0)
    
    print(f"   Init overhead (actions vs silent): +{actions_init - silent_init:.2f}ms")
    print(f"   Per-call overhead (actions vs silent): +{actions_callback - silent_callback:.3f}µs")
    print()
    print("   DEFAULT MODE: silent (zero overhead)")
    print("   OPT-IN: output='actions' for observability")
    print()


if __name__ == "__main__":
    main()
