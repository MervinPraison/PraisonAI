#!/usr/bin/env python3
"""
PraisonAI Benchmark Example

This example demonstrates how to use the benchmark system programmatically
to compare performance across different execution paths.

Usage:
    python benchmark_example.py
    
Requirements:
    - OPENAI_API_KEY environment variable set
    - praisonai package installed
"""

import os
import sys

# Ensure the package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/praisonai'))

from praisonai.cli.features.benchmark import BenchmarkHandler, BenchmarkReport


def run_quick_comparison():
    """Run a quick comparison of key execution paths."""
    print("=" * 60)
    print("Quick Benchmark Comparison")
    print("=" * 60)
    
    handler = BenchmarkHandler()
    
    # Run benchmark with 2 iterations on key paths
    report = handler.run_full_benchmark(
        prompt="What is 2+2?",
        iterations=2,
        paths=["openai_sdk", "praisonai_agent"],
        verbose=True
    )
    
    # Print comparison table
    print("\n" + handler.create_comparison_table(report))
    
    return report


def run_full_benchmark():
    """Run full benchmark suite across all paths."""
    print("=" * 60)
    print("Full Benchmark Suite")
    print("=" * 60)
    
    handler = BenchmarkHandler()
    
    # Run full benchmark
    report = handler.run_full_benchmark(
        prompt="Hi",
        iterations=3,
        verbose=True
    )
    
    # Print full report
    handler.print_report(report)
    
    return report


def run_agent_benchmark():
    """Benchmark PraisonAI Agent specifically."""
    print("=" * 60)
    print("Agent Benchmark")
    print("=" * 60)
    
    handler = BenchmarkHandler()
    
    # Benchmark agent vs SDK
    report = handler.run_full_benchmark(
        prompt="Explain Python in one sentence",
        iterations=3,
        paths=["openai_sdk", "praisonai_agent"],
        verbose=True
    )
    
    # Show timeline diagrams
    for name, result in report.results.items():
        print(f"\n### {name}")
        print(handler.create_timeline_diagram(result))
    
    # Show variance analysis
    print(handler.create_variance_table(report))
    
    return report


def save_benchmark_results(report: BenchmarkReport, output_path: str):
    """Save benchmark results to JSON file."""
    import json
    
    with open(output_path, 'w') as f:
        json.dump(report.to_dict(), f, indent=2)
    
    print(f"\nResults saved to: {output_path}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="PraisonAI Benchmark Example")
    parser.add_argument(
        "--mode",
        choices=["quick", "full", "agent"],
        default="quick",
        help="Benchmark mode: quick (2 paths), full (all paths), agent (agent focus)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path"
    )
    
    args = parser.parse_args()
    
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    # Run selected benchmark
    if args.mode == "quick":
        report = run_quick_comparison()
    elif args.mode == "full":
        report = run_full_benchmark()
    elif args.mode == "agent":
        report = run_agent_benchmark()
    
    # Save results if requested
    if args.output:
        save_benchmark_results(report, args.output)
    
    print("\n✅ Benchmark complete!")


if __name__ == "__main__":
    main()
