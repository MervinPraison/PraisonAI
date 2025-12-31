"""
Profile Suite Example for PraisonAI

This example demonstrates how to run a comprehensive profiling suite
programmatically with multiple scenarios.

Run with:
    python suite_profiling.py
"""

import os

# Ensure API key is set
if not os.environ.get("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY environment variable")
    exit(1)

from praisonai.cli.features.profiler import (
    ScenarioConfig,
    run_profile_suite,
)


def main():
    """Run a profiling suite with custom scenarios."""
    
    # Define custom scenarios
    scenarios = [
        ScenarioConfig(
            name="simple_query",
            prompt="What is 2+2?",
            stream=False,
            iterations=2,
            warmup=1,
        ),
        ScenarioConfig(
            name="simple_stream",
            prompt="What is 2+2?",
            stream=True,
            iterations=2,
            warmup=1,
        ),
    ]
    
    # Run suite with custom output directory
    print("🔬 Running Profile Suite...")
    result = run_profile_suite(
        output_dir="./profile_results",
        scenarios=scenarios,
        verbose=True,
    )
    
    # Print summary
    print("\n" + "=" * 60)
    print("Profile Suite Results")
    print("=" * 60)
    
    print("\n📊 Startup Times:")
    print(f"  Cold Start: {result.startup_cold_ms:.2f}ms")
    print(f"  Warm Start: {result.startup_warm_ms:.2f}ms")
    
    if result.import_analysis:
        print("\n📦 Top Import:")
        print(f"  {result.import_analysis[0]['module']}: {result.import_analysis[0]['cumulative_ms']:.2f}ms")
    
    print("\n🎯 Scenario Results:")
    for scenario in result.scenarios:
        stats = scenario.get_stats(scenario.total_times)
        print(f"  {scenario.name}:")
        print(f"    Mean: {stats['mean']:.2f}ms")
        print(f"    Min:  {stats['min']:.2f}ms")
        print(f"    Max:  {stats['max']:.2f}ms")
    
    print("\n✅ Results saved to: ./profile_results/")
    print("   - suite_results.json (machine-readable)")
    print("   - suite_report.txt (human-readable)")


if __name__ == "__main__":
    main()
