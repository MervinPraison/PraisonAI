#!/usr/bin/env python3
"""
Memory usage benchmark for praisonaiagents.

This benchmark measures the memory footprint of importing praisonaiagents
and verifies it stays within acceptable limits.

Usage:
    python benchmarks/memory_usage.py
    
CI Gate:
    - PASS: memory < 30MB
    - WARN: memory 30-45MB
    - FAIL: memory > 45MB
"""
import sys
import tracemalloc
import argparse


def clear_modules():
    """Clear all praisonai and litellm related modules from cache."""
    to_remove = [m for m in sys.modules.keys() 
                 if 'praison' in m or 'litellm' in m]
    for mod in to_remove:
        del sys.modules[mod]


def measure_memory() -> dict:
    """
    Measure memory usage after importing praisonaiagents.
    
    Returns:
        dict with current and peak memory in MB
    """
    clear_modules()
    
    tracemalloc.start()
    
    import praisonaiagents  # noqa: F401
    
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    return {
        'current_bytes': current,
        'peak_bytes': peak,
        'current_mb': current / 1024 / 1024,
        'peak_mb': peak / 1024 / 1024,
    }


def main():
    """Run the benchmark and print results."""
    print("=" * 60)
    print("PraisonAI Agents Memory Usage Benchmark")
    print("=" * 60)
    
    print("\nMeasuring memory usage...")
    results = measure_memory()
    
    print(f"\nMemory Usage:")
    print(f"  Current: {results['current_mb']:.1f} MB")
    print(f"  Peak:    {results['peak_mb']:.1f} MB")
    
    # Determine pass/fail based on peak memory
    peak_mb = results['peak_mb']
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    if peak_mb < 30:
        status = "PASS"
        msg = f"Memory {peak_mb:.1f}MB < 30MB target"
    elif peak_mb < 45:
        status = "WARN"
        msg = f"Memory {peak_mb:.1f}MB between 30-45MB"
    else:
        status = "FAIL"
        msg = f"Memory {peak_mb:.1f}MB > 45MB limit"
    
    print(f"\nMemory: [{status}] {msg}")
    
    # Exit code for CI
    return 0 if status != "FAIL" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='PraisonAI Agents Memory Usage Benchmark')
    parser.add_argument('--save', action='store_true', help='Save results to file')
    args = parser.parse_args()
    
    if not args.save:
        print("\nNote: Results are not saved to file by default. Use --save to save them.")
        
    sys.exit(main())
