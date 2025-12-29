"""
Performance Benchmark Example for PraisonAI.

This example demonstrates how to measure and verify performance metrics
for PraisonAI CLI and SDK imports.

Usage:
    python benchmark_example.py
"""

import time
import tracemalloc
import sys


def measure_import_time(module_name: str) -> float:
    """Measure import time for a module."""
    # Clear from cache if already imported
    if module_name in sys.modules:
        del sys.modules[module_name]
    
    start = time.time()
    __import__(module_name)
    elapsed = time.time() - start
    return elapsed * 1000  # Return milliseconds


def measure_memory_usage(import_func) -> tuple:
    """Measure memory usage during import."""
    tracemalloc.start()
    import_func()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return current / 1024 / 1024, peak / 1024 / 1024  # Return MB


def main():
    print("=" * 60)
    print("PraisonAI Performance Benchmark")
    print("=" * 60)
    
    # Test 1: CLI Import Time
    print("\n1. CLI Import Time")
    print("-" * 40)
    
    import os
    os.environ['LOGLEVEL'] = 'WARNING'
    
    start = time.time()
    from praisonai.cli.main import PraisonAI
    cli_import_time = (time.time() - start) * 1000
    
    print(f"   CLI import time: {cli_import_time:.0f}ms")
    print(f"   Status: {'✓ FAST' if cli_import_time < 500 else '✗ SLOW'}")
    
    # Test 2: Memory Usage
    print("\n2. Memory Usage")
    print("-" * 40)
    
    tracemalloc.start()
    # Force re-import by clearing cache
    for mod in list(sys.modules.keys()):
        if 'praisonai' in mod:
            del sys.modules[mod]
    
    from praisonai.cli.main import PraisonAI as PraisonAI2
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    print(f"   Current memory: {current/1024/1024:.1f}MB")
    print(f"   Peak memory: {peak/1024/1024:.1f}MB")
    print(f"   Status: {'✓ LOW' if peak/1024/1024 < 50 else '✗ HIGH'}")
    
    # Test 3: Lazy Loading Verification
    print("\n3. Lazy Loading Verification")
    print("-" * 40)
    
    heavy_modules = ['litellm', 'instructor', 'praisonai.auto']
    loaded = [m for m in heavy_modules if m in sys.modules]
    
    if loaded:
        print(f"   Heavy modules loaded: {loaded}")
        print("   Status: ✗ NOT LAZY")
    else:
        print("   Heavy modules NOT loaded at startup")
        print("   Status: ✓ LAZY")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_pass = (
        cli_import_time < 500 and
        peak/1024/1024 < 50 and
        len(loaded) == 0
    )
    
    if all_pass:
        print("✓ All performance benchmarks PASSED")
    else:
        print("✗ Some benchmarks FAILED")
    
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
