#!/usr/bin/env python3
"""
PraisonAI Agents - Tools Benchmark

Compares agent instantiation times WITH TOOLS across frameworks.

Usage:
    python benchmarks/tools_benchmark.py
"""

import time
from typing import Literal
from importlib.metadata import version as get_version


ITERATIONS = 100


def sample_tool(city: Literal['nyc', 'sf']):
    """Sample tool for benchmark testing."""
    if city == 'nyc':
        return 'cloudy'
    return 'sunny'


def measure_instantiation(create_fn, iterations=ITERATIONS):
    """Measure average instantiation time in microseconds."""
    times = []
    
    # Warmup
    for _ in range(10):
        create_fn()
    
    # Measure
    for _ in range(iterations):
        start = time.perf_counter()
        create_fn()
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1_000_000)  # Convert to microseconds
    
    return sum(times) / len(times)


def run_benchmark():
    """Run the benchmark across all available frameworks WITH TOOLS."""
    tools = [sample_tool]
    results = {}
    
    print('=' * 60)
    print('PraisonAI Agents - Tools Benchmark')
    print('=' * 60)
    print(f'\nIterations: {ITERATIONS}')
    print('Metric: Agent instantiation time WITH TOOLS (microseconds)\n')
    
    # PraisonAI with tools
    print("Testing PraisonAI...")
    from praisonaiagents import Agent as PraisonAgent
    
    results['PraisonAI'] = measure_instantiation(
        lambda: PraisonAgent(name='Test', llm='gpt-4o-mini', tools=tools, verbose=False)
    )
    
    results['PraisonAI (LiteLLM)'] = measure_instantiation(
        lambda: PraisonAgent(name='Test', llm='openai/gpt-4o-mini', tools=tools, verbose=False)
    )
    
    # Other frameworks with tools
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
        from agents import Agent as OpenAIAgent, function_tool
        results['OpenAI Agents SDK'] = measure_instantiation(
            lambda: OpenAIAgent(name='Test', model='gpt-4o-mini', tools=[function_tool(sample_tool)])
        )
    except ImportError:
        pass
    
    try:
        from langchain_core.tools import tool as langchain_tool
        from langchain_openai import ChatOpenAI
        from langgraph.prebuilt import create_react_agent
        
        @langchain_tool
        def get_weather_lg(city: Literal['nyc', 'sf']):
            """Get weather info."""
            return 'sunny' if city == 'sf' else 'cloudy'
        
        results['LangGraph'] = measure_instantiation(
            lambda: create_react_agent(model=ChatOpenAI(model='gpt-4o-mini'), tools=[get_weather_lg])
        )
    except ImportError:
        pass
    
    try:
        from crewai.agent import Agent as CrewAgent
        from crewai.tools import tool as crewai_tool
        
        @crewai_tool("Weather Tool")
        def get_weather_crew(city: Literal['nyc', 'sf']):
            """Get weather info."""
            return 'sunny' if city == 'sf' else 'cloudy'
        
        results['CrewAI'] = measure_instantiation(
            lambda: CrewAgent(
                role='Weather Agent',
                goal='Provide weather info',
                backstory='A weather expert',
                tools=[get_weather_crew],
                verbose=False
            )
        )
    except ImportError:
        pass
    
    # Print results
    print('\n' + '=' * 60)
    print('RESULTS (WITH TOOLS)')
    print('=' * 60)
    
    sorted_results = sorted(results.items(), key=lambda x: x[1])
    baseline = sorted_results[0][1] if sorted_results else 1
    
    print(f"\n{'Framework':<25} {'Avg Time (μs)':<15} {'Relative':<10}")
    print('-' * 50)
    
    for name, avg in sorted_results:
        ratio = avg / baseline
        print(f'{name:<25} {avg:<15.2f} {ratio:.2f}x')
    
    print('\n' + '=' * 60)
    return results


def get_package_versions():
    """Get version numbers for benchmarked packages."""
    packages = {
        'PraisonAI': 'praisonaiagents',
        'Agno': 'agno',
        'OpenAI Agents SDK': 'openai-agents',
        'LangGraph': 'langgraph',
        'CrewAI': 'crewai'
    }
    
    versions = {}
    for display_name, pkg_name in packages.items():
        try:
            versions[display_name] = get_version(pkg_name)
        except Exception:
            versions[display_name] = 'not installed'
    
    return versions


def save_results(results: dict, filename: str = 'TOOLS_BENCHMARK_RESULTS.md'):
    """Save benchmark results to a markdown file."""
    import os
    from datetime import datetime
    
    filepath = os.path.join(os.path.dirname(__file__), filename)
    versions = get_package_versions()
    
    # Find the fastest result (baseline)
    sorted_results = sorted(results.items(), key=lambda x: x[1])
    fastest_time = sorted_results[0][1] if sorted_results else 1
    
    # Build the table rows
    table_rows = []
    for name, avg in sorted_results:
        ratio = avg / fastest_time
        if ratio == 1.0:
            table_rows.append(f'| **{name}** | **{avg:.2f}** | **1.00x (fastest)** |')
        else:
            avg_str = f'{avg:,.2f}' if avg >= 1000 else f'{avg:.2f}'
            ratio_str = f'{ratio:,.0f}x' if ratio >= 100 else f'{ratio:.2f}x'
            table_rows.append(f'| {name} | {avg_str} | {ratio_str} |')
    
    # Save to file
    with open(filepath, 'w') as f:
        f.write('# PraisonAI Agents - Tools Benchmark Results\n\n')
        f.write(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'**Iterations:** {ITERATIONS}\n')
        f.write('**Test:** Agent instantiation WITH TOOLS\n\n')
        f.write('## Results\n\n')
        f.write('| Framework | Avg Time (μs) | Relative |\n')
        f.write('|-----------|---------------|----------|\n')
        f.write('\n'.join(table_rows) + '\n')
        f.write('\n## Package Versions\n\n')
        f.write('| Package | Version |\n')
        f.write('|---------|--------|\n')
        for pkg, ver in versions.items():
            f.write(f'| {pkg} | {ver} |\n')
        f.write('\n## How to Reproduce\n\n')
        f.write('```bash\n')
        f.write('cd praisonai-agents\n')
        f.write('python benchmarks/tools_benchmark.py\n')
        f.write('```\n')
    
    print(f'\nResults saved to: {filepath}')
    return filepath


if __name__ == '__main__':
    results = run_benchmark()
    save_results(results)
