#!/usr/bin/env python3
"""
PraisonAI Agents - Performance Benchmark

Compares agent instantiation times across popular AI agent frameworks.

Usage:
    python benchmarks/simple_benchmark.py
"""

import time
from typing import Literal


ITERATIONS = 100


def sample_tool(city: Literal['nyc', 'sf']):
    """Sample tool for benchmark testing."""
    if city == 'nyc':
        return 'cloudy'
    return 'sunny'


def measure_instantiation(create_fn, iterations=ITERATIONS):
    """Measure average instantiation time in microseconds."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        create_fn()
        times.append((time.perf_counter() - start) * 1_000_000)
    return sum(times) / len(times)


def run_benchmark():
    """Run the benchmark across all available frameworks."""
    tools = [sample_tool]
    results = {}
    
    print('=' * 60)
    print('PraisonAI Agents - Performance Benchmark')
    print('=' * 60)
    print(f'\nIterations: {ITERATIONS}')
    print('Metric: Agent instantiation time (microseconds)\n')
    
    # PraisonAI
    print("Testing PraisonAI...")
    from praisonaiagents import Agent as PraisonAgent
    results['PraisonAI'] = measure_instantiation(
        lambda: PraisonAgent(name='Test', llm='gpt-4o-mini', tools=tools, verbose=False)
    )
    
    results['PraisonAI (LiteLLM)'] = measure_instantiation(
        lambda: PraisonAgent(name='Test', llm='openai/gpt-4o-mini', tools=tools, verbose=False)
    )
    
    # Other frameworks for comparison
    print("Testing other frameworks...")
    
    try:
        from agno.agent import Agent as AgnoAgent
        from agno.models.openai import OpenAIChat
        results['Agno'] = measure_instantiation(
            lambda: AgnoAgent(model=OpenAIChat(id='gpt-4o-mini'), tools=tools)
        )
    except ImportError:
        pass
    
    try:
        from pydantic_ai import Agent as PydanticAgent
        results['PydanticAI'] = measure_instantiation(
            lambda: PydanticAgent('openai:gpt-4o-mini')
        )
    except ImportError:
        pass
    
    try:
        from agents import Agent as OpenAIAgent
        results['OpenAI Agents SDK'] = measure_instantiation(
            lambda: OpenAIAgent(name='Test', model='gpt-4o-mini')
        )
    except ImportError:
        pass
    
    # Print results
    print('\n' + '=' * 60)
    print('RESULTS')
    print('=' * 60)
    
    baseline = results.get('PraisonAI', 1)
    print(f"\n{'Framework':<25} {'Avg Time (μs)':<15} {'Relative':<10}")
    print('-' * 50)
    
    for name, avg in sorted(results.items(), key=lambda x: x[1]):
        ratio = avg / baseline
        print(f'{name:<25} {avg:<15.2f} {ratio:.2f}x')
    
    print('\n' + '=' * 60)
    return results


if __name__ == '__main__':
    run_benchmark()
