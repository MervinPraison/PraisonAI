#!/usr/bin/env python3
"""
PraisonAI Agents - Parameter Impact Benchmark

Profiles each Agent parameter to identify which features have the most
performance impact. Results are ordered by cost (time + memory).

This benchmark helps identify optimization opportunities by measuring
the incremental cost of each feature.

Usage:
    python benchmarks/param_impact_benchmark.py
    python benchmarks/param_impact_benchmark.py --no-save
    python benchmarks/param_impact_benchmark.py --iterations 50
"""

import argparse
import gc
import time
import tracemalloc
import statistics
from typing import Literal, List, Dict, Any, Callable
from dataclasses import dataclass


@dataclass
class ParamResult:
    """Result for a single parameter test."""
    param_name: str
    param_value: Any
    avg_time_us: float  # microseconds
    min_time_us: float
    max_time_us: float
    std_dev_us: float
    avg_memory_kb: float  # kilobytes
    delta_time_us: float = 0.0  # difference from baseline
    delta_memory_kb: float = 0.0


def measure_instantiation(
    create_fn: Callable,
    iterations: int = 100,
    warmup: int = 10
) -> Dict[str, float]:
    """Measure instantiation time and memory for a function."""
    # Warmup
    for _ in range(warmup):
        create_fn()
    
    # Measure time
    times = []
    for _ in range(iterations):
        gc.collect()
        start = time.perf_counter()
        create_fn()
        elapsed = (time.perf_counter() - start) * 1_000_000  # microseconds
        times.append(elapsed)
    
    # Measure memory (separate pass for accuracy)
    memory_usages = []
    for _ in range(min(iterations, 20)):  # Fewer iterations for memory
        gc.collect()
        tracemalloc.start()
        create_fn()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory_usages.append(peak / 1024)  # KB
    
    return {
        'avg_time': statistics.mean(times),
        'min_time': min(times),
        'max_time': max(times),
        'std_dev': statistics.stdev(times) if len(times) > 1 else 0,
        'avg_memory': statistics.mean(memory_usages) if memory_usages else 0,
    }


def sample_tool(city: Literal['nyc', 'sf']):
    """Sample tool for benchmark testing."""
    return 'cloudy' if city == 'nyc' else 'sunny'


def run_benchmark(iterations: int = 100) -> List[ParamResult]:
    """Run parameter impact benchmark."""
    from praisonaiagents import Agent
    
    results = []
    
    print('=' * 70)
    print('PraisonAI Agents - Parameter Impact Benchmark')
    print('=' * 70)
    print(f'\nIterations: {iterations}')
    print('Measuring incremental cost of each Agent parameter\n')
    
    # Baseline: Minimal agent
    print("Testing baseline (minimal agent)...")
    baseline_stats = measure_instantiation(
        lambda: Agent(name='Test', output='silent'),
        iterations
    )
    baseline_result = ParamResult(
        param_name='BASELINE',
        param_value='Agent(name="Test", output="silent")',
        avg_time_us=baseline_stats['avg_time'],
        min_time_us=baseline_stats['min_time'],
        max_time_us=baseline_stats['max_time'],
        std_dev_us=baseline_stats['std_dev'],
        avg_memory_kb=baseline_stats['avg_memory'],
    )
    results.append(baseline_result)
    print(f"  Baseline: {baseline_stats['avg_time']:.2f} μs, {baseline_stats['avg_memory']:.2f} KB")
    
    # Define parameters to test
    # Format: (param_name, param_value, description)
    params_to_test = [
        # Core identity
        ('instructions', 'Be helpful and concise.', 'instructions="..."'),
        ('role', 'Assistant', 'role="Assistant"'),
        ('goal', 'Help users', 'goal="Help users"'),
        ('backstory', 'I am an AI assistant.', 'backstory="..."'),
        
        # LLM configuration
        ('llm', 'gpt-4o-mini', 'llm="gpt-4o-mini"'),
        ('llm', 'openai/gpt-4o-mini', 'llm="openai/gpt-4o-mini" (LiteLLM)'),
        
        # Tools
        ('tools', [sample_tool], 'tools=[sample_tool]'),
        
        # Features (bool flags)
        ('context', True, 'context=True'),
        ('context', False, 'context=False'),
        ('planning', True, 'planning=True'),
        ('reflection', True, 'reflection=True'),
        ('memory', True, 'memory=True'),
        
        # Output modes
        ('output', 'verbose', 'output="verbose"'),
        ('output', 'actions', 'output="actions"'),
        ('output', 'stream', 'output="stream"'),
        
        # Execution config
        ('execution', 'fast', 'execution="fast"'),
        ('execution', 'thorough', 'execution="thorough"'),
        
        # Caching
        ('caching', True, 'caching=True'),
        ('caching', False, 'caching=False'),
    ]
    
    # Test each parameter
    for param_name, param_value, description in params_to_test:
        print(f"Testing {description}...")
        
        try:
            # Build kwargs
            kwargs = {'name': 'Test', 'output': 'silent'}
            kwargs[param_name] = param_value
            
            # Special case: if testing output param, don't override with silent
            if param_name == 'output':
                kwargs = {'name': 'Test'}
                kwargs[param_name] = param_value
            
            stats = measure_instantiation(
                lambda k=kwargs: Agent(**k),
                iterations
            )
            
            result = ParamResult(
                param_name=param_name,
                param_value=description,
                avg_time_us=stats['avg_time'],
                min_time_us=stats['min_time'],
                max_time_us=stats['max_time'],
                std_dev_us=stats['std_dev'],
                avg_memory_kb=stats['avg_memory'],
                delta_time_us=stats['avg_time'] - baseline_stats['avg_time'],
                delta_memory_kb=stats['avg_memory'] - baseline_stats['avg_memory'],
            )
            results.append(result)
            
            delta_sign = '+' if result.delta_time_us >= 0 else ''
            print(f"  {stats['avg_time']:.2f} μs ({delta_sign}{result.delta_time_us:.2f} μs from baseline)")
            
        except Exception as e:
            print(f"  SKIPPED: {e}")
    
    return results


def print_results(results: List[ParamResult]):
    """Print results sorted by performance impact."""
    print('\n' + '=' * 70)
    print('RESULTS - Sorted by Time Impact (highest cost first)')
    print('=' * 70)
    
    # Sort by delta time (excluding baseline)
    sorted_results = sorted(
        [r for r in results if r.param_name != 'BASELINE'],
        key=lambda x: x.delta_time_us,
        reverse=True
    )
    
    # Get baseline
    baseline = next((r for r in results if r.param_name == 'BASELINE'), None)
    
    if baseline:
        print(f"\nBaseline: {baseline.avg_time_us:.2f} μs, {baseline.avg_memory_kb:.2f} KB")
    
    print(f"\n{'Parameter':<35} {'Avg (μs)':<12} {'Delta (μs)':<12} {'Memory (KB)':<12} {'Impact':<10}")
    print('-' * 85)
    
    for r in sorted_results:
        # Calculate impact level
        if r.delta_time_us > 1000:
            impact = '🔴 HIGH'
        elif r.delta_time_us > 100:
            impact = '🟡 MEDIUM'
        elif r.delta_time_us > 10:
            impact = '🟢 LOW'
        else:
            impact = '⚪ MINIMAL'
        
        delta_str = f"+{r.delta_time_us:.2f}" if r.delta_time_us >= 0 else f"{r.delta_time_us:.2f}"
        print(f"{r.param_value:<35} {r.avg_time_us:<12.2f} {delta_str:<12} {r.avg_memory_kb:<12.2f} {impact:<10}")
    
    # Summary
    print('\n' + '=' * 70)
    print('SUMMARY')
    print('=' * 70)
    
    high_impact = [r for r in sorted_results if r.delta_time_us > 1000]
    medium_impact = [r for r in sorted_results if 100 < r.delta_time_us <= 1000]
    low_impact = [r for r in sorted_results if 10 < r.delta_time_us <= 100]
    
    print(f"\nHigh impact (>1ms): {len(high_impact)} parameters")
    for r in high_impact:
        print(f"  - {r.param_value}: +{r.delta_time_us:.2f} μs")
    
    print(f"\nMedium impact (100μs-1ms): {len(medium_impact)} parameters")
    for r in medium_impact:
        print(f"  - {r.param_value}: +{r.delta_time_us:.2f} μs")
    
    print(f"\nLow impact (10-100μs): {len(low_impact)} parameters")
    
    print('\n' + '=' * 70)


def save_results(results: List[ParamResult], filename: str = 'PARAM_IMPACT_RESULTS.md'):
    """Save results to markdown file."""
    import os
    from datetime import datetime
    
    filepath = os.path.join(os.path.dirname(__file__), filename)
    
    # Sort by delta time
    sorted_results = sorted(
        [r for r in results if r.param_name != 'BASELINE'],
        key=lambda x: x.delta_time_us,
        reverse=True
    )
    baseline = next((r for r in results if r.param_name == 'BASELINE'), None)
    
    with open(filepath, 'w') as f:
        f.write('# PraisonAI Agents - Parameter Impact Benchmark Results\n\n')
        f.write(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n')
        
        if baseline:
            f.write(f'**Baseline:** {baseline.avg_time_us:.2f} μs, {baseline.avg_memory_kb:.2f} KB\n\n')
        
        f.write('## Results (Sorted by Impact)\n\n')
        f.write('| Parameter | Avg Time (μs) | Delta (μs) | Memory (KB) | Impact |\n')
        f.write('|-----------|---------------|------------|-------------|--------|\n')
        
        for r in sorted_results:
            if r.delta_time_us > 1000:
                impact = '🔴 HIGH'
            elif r.delta_time_us > 100:
                impact = '🟡 MEDIUM'
            elif r.delta_time_us > 10:
                impact = '🟢 LOW'
            else:
                impact = '⚪ MINIMAL'
            
            delta_str = f"+{r.delta_time_us:.2f}" if r.delta_time_us >= 0 else f"{r.delta_time_us:.2f}"
            f.write(f'| {r.param_value} | {r.avg_time_us:.2f} | {delta_str} | {r.avg_memory_kb:.2f} | {impact} |\n')
        
        f.write('\n## Recommendations\n\n')
        
        high_impact = [r for r in sorted_results if r.delta_time_us > 1000]
        if high_impact:
            f.write('### High Impact Parameters (>1ms)\n\n')
            f.write('These parameters add significant overhead and should be used carefully:\n\n')
            for r in high_impact:
                f.write(f'- **{r.param_value}**: +{r.delta_time_us:.2f} μs\n')
            f.write('\n')
        
        f.write('### Best Practices\n\n')
        f.write('1. Use `output="silent"` for production workloads\n')
        f.write('2. Only enable `context=True` when needed for long conversations\n')
        f.write('3. Use `llm="gpt-4o-mini"` (OpenAI SDK) for fastest instantiation\n')
        f.write('4. Avoid `memory=True` unless persistent memory is required\n')
        
        f.write('\n## How to Reproduce\n\n')
        f.write('```bash\n')
        f.write('cd praisonai-agents\n')
        f.write('python benchmarks/param_impact_benchmark.py\n')
        f.write('```\n')
    
    print(f'\nResults saved to: {filepath}')
    return filepath


def main():
    parser = argparse.ArgumentParser(description='PraisonAI Parameter Impact Benchmark')
    parser.add_argument('--iterations', type=int, default=100, help='Number of iterations per test')
    parser.add_argument('--no-save', action='store_true', help='Do not save results to file')
    args = parser.parse_args()
    
    results = run_benchmark(iterations=args.iterations)
    print_results(results)
    
    if not args.no_save:
        save_results(results)


if __name__ == '__main__':
    main()
