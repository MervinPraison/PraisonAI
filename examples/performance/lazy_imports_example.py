#!/usr/bin/env python3
"""
Example: Lazy Imports & Fast Startup

Demonstrates how PraisonAI Agents uses lazy imports to achieve
fast startup times and reduced memory usage.
"""
import sys
import time


def example_verify_lazy_imports():
    """Verify that heavy dependencies are not loaded at import time."""
    print("=" * 60)
    print("Lazy Imports Verification")
    print("=" * 60)
    
    # Clear any cached imports
    heavy_deps = ['litellm', 'chromadb', 'mem0', 'requests']
    for dep in heavy_deps:
        for key in list(sys.modules.keys()):
            if key.startswith(dep):
                del sys.modules[key]
    
    # Measure import time
    start = time.perf_counter()
    import praisonaiagents
    elapsed = (time.perf_counter() - start) * 1000
    
    print(f"\nImport time: {elapsed:.1f}ms")
    print(f"Target: <200ms")
    print(f"Status: {'PASS' if elapsed < 200 else 'FAIL'}")
    
    # Check lazy imports
    print("\nLazy Import Check:")
    all_lazy = True
    for dep in heavy_deps:
        is_lazy = dep not in sys.modules
        status = "LAZY (good)" if is_lazy else "EAGER (bad)"
        print(f"  {dep}: {status}")
        if not is_lazy:
            all_lazy = False
    
    print(f"\nAll lazy: {'PASS' if all_lazy else 'FAIL'}")
    return all_lazy


def example_measure_memory():
    """Measure memory usage after import."""
    print("\n" + "=" * 60)
    print("Memory Usage Measurement")
    print("=" * 60)
    
    import tracemalloc
    
    # Clear modules
    for key in list(sys.modules.keys()):
        if key.startswith('praisonaiagents'):
            del sys.modules[key]
    
    tracemalloc.start()
    import praisonaiagents
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    current_mb = current / 1024 / 1024
    peak_mb = peak / 1024 / 1024
    
    print(f"\nCurrent memory: {current_mb:.1f}MB")
    print(f"Peak memory: {peak_mb:.1f}MB")
    print(f"Target: <30MB")
    print(f"Status: {'PASS' if current_mb < 30 else 'WARN' if current_mb < 45 else 'FAIL'}")
    
    return current_mb < 45


def example_specific_imports():
    """Show how to use specific imports for best performance."""
    print("\n" + "=" * 60)
    print("Specific Imports Example")
    print("=" * 60)
    
    # Good - specific imports are fast
    print("\nGood practice - specific imports:")
    print("  from praisonaiagents import Agent, Task")
    
    # Avoid - star imports load everything
    print("\nAvoid - star imports load more:")
    print("  from praisonaiagents import *")
    
    # Example of specific import
    from praisonaiagents import Agent
    print(f"\nAgent class loaded: {Agent.__name__}")


if __name__ == "__main__":
    print("PraisonAI Agents - Lazy Imports Example")
    print("=" * 60)
    
    # Run examples
    lazy_ok = example_verify_lazy_imports()
    memory_ok = example_measure_memory()
    example_specific_imports()
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Lazy imports: {'PASS' if lazy_ok else 'FAIL'}")
    print(f"Memory usage: {'PASS' if memory_ok else 'FAIL'}")
    print(f"Overall: {'PASS' if lazy_ok and memory_ok else 'FAIL'}")
