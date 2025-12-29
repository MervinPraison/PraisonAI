#!/usr/bin/env python3
"""
Import time benchmark for praisonaiagents.

This benchmark measures the import time of the praisonaiagents package
and verifies that heavy dependencies are not loaded at import time.

Usage:
    python benchmarks/import_time.py
    
CI Gate:
    - PASS: import time < 200ms
    - WARN: import time 200-300ms
    - FAIL: import time > 300ms
"""
import sys
import time
import statistics


def clear_modules():
    """Clear all praisonai and litellm related modules from cache."""
    to_remove = [m for m in sys.modules.keys() 
                 if 'praison' in m or 'litellm' in m]
    for mod in to_remove:
        del sys.modules[mod]


def measure_import_time(runs: int = 5) -> dict:
    """
    Measure import time over multiple runs.
    
    Returns:
        dict with min, max, median, mean times in milliseconds
    """
    times = []
    
    for _ in range(runs):
        clear_modules()
        
        start = time.perf_counter()
        import praisonaiagents  # noqa: F401
        end = time.perf_counter()
        
        times.append((end - start) * 1000)
        
        # Clean up for next run
        if 'praisonaiagents' in sys.modules:
            del sys.modules['praisonaiagents']
    
    times.sort()
    
    return {
        'times': times,
        'min': min(times),
        'max': max(times),
        'median': statistics.median(times),
        'mean': statistics.mean(times),
        'stdev': statistics.stdev(times) if len(times) > 1 else 0,
    }


def check_lazy_imports() -> dict:
    """
    Check that heavy dependencies are NOT loaded after importing praisonaiagents.
    
    Returns:
        dict with module names and whether they are loaded
    """
    clear_modules()
    
    import praisonaiagents  # noqa: F401
    
    heavy_modules = [
        'litellm',
        'chromadb', 
        'mem0',
        'requests',
    ]
    
    results = {}
    for mod in heavy_modules:
        results[mod] = mod in sys.modules
    
    return results


def main():
    """Run the benchmark and print results."""
    print("=" * 60)
    print("PraisonAI Agents Import Time Benchmark")
    print("=" * 60)
    
    # Measure import time
    print("\n[1/2] Measuring import time (5 runs)...")
    results = measure_import_time(runs=5)
    
    print(f"\nImport times (ms): {[round(t, 1) for t in results['times']]}")
    print(f"  Min:    {results['min']:.1f} ms")
    print(f"  Max:    {results['max']:.1f} ms")
    print(f"  Median: {results['median']:.1f} ms")
    print(f"  Mean:   {results['mean']:.1f} ms")
    print(f"  StdDev: {results['stdev']:.1f} ms")
    
    # Check lazy imports
    print("\n[2/2] Checking lazy imports...")
    lazy_results = check_lazy_imports()
    
    print("\nHeavy modules loaded at import time:")
    all_lazy = True
    for mod, loaded in lazy_results.items():
        status = "LOADED (BAD)" if loaded else "NOT LOADED (GOOD)"
        print(f"  {mod}: {status}")
        if loaded:
            all_lazy = False
    
    # Determine pass/fail
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    median_time = results['median']
    
    if median_time < 200:
        time_status = "PASS"
        time_msg = f"Import time {median_time:.0f}ms < 200ms target"
    elif median_time < 300:
        time_status = "WARN"
        time_msg = f"Import time {median_time:.0f}ms between 200-300ms"
    else:
        time_status = "FAIL"
        time_msg = f"Import time {median_time:.0f}ms > 300ms limit"
    
    lazy_status = "PASS" if all_lazy else "FAIL"
    lazy_msg = "All heavy deps lazy loaded" if all_lazy else "Some heavy deps loaded eagerly"
    
    print(f"\nImport Time: [{time_status}] {time_msg}")
    print(f"Lazy Imports: [{lazy_status}] {lazy_msg}")
    
    overall = "PASS" if time_status != "FAIL" and lazy_status == "PASS" else "FAIL"
    print(f"\nOverall: [{overall}]")
    
    # Exit code for CI
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
