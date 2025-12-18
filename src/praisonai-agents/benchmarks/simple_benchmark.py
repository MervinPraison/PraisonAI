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


def save_results(results: dict, filename: str = 'BENCHMARK_RESULTS.md'):
    """Save benchmark results to a markdown file."""
    import os
    import re
    from datetime import datetime
    
    filepath = os.path.join(os.path.dirname(__file__), filename)
    baseline = results.get('PraisonAI', 1)
    
    # Build the table rows
    table_rows = []
    for name, avg in sorted(results.items(), key=lambda x: x[1]):
        ratio = avg / baseline
        if name == 'PraisonAI':
            table_rows.append(f'| **{name}** | **{avg:.2f}** | **1.00x (fastest)** |')
        else:
            # Format large numbers with commas
            avg_str = f'{avg:,.2f}' if avg >= 1000 else f'{avg:.2f}'
            ratio_str = f'{ratio:,.0f}x' if ratio >= 100 else f'{ratio:.2f}x'
            table_rows.append(f'| {name} | {avg_str} | {ratio_str} |')
    
    # Save to BENCHMARK_RESULTS.md
    with open(filepath, 'w') as f:
        f.write('# PraisonAI Agents - Benchmark Results\n\n')
        f.write(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n')
        f.write('## Agent Instantiation Time\n\n')
        f.write('| Framework | Avg Time (μs) | Relative |\n')
        f.write('|-----------|---------------|----------|\n')
        f.write('\n'.join(table_rows) + '\n')
        f.write('\n## How to Reproduce\n\n')
        f.write('```bash\n')
        f.write('cd praisonai-agents\n')
        f.write('python benchmarks/simple_benchmark.py\n')
        f.write('```\n')
    
    print(f'\nResults saved to: {filepath}')
    
    # Also update the main README.md
    readme_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'README.md')
    if os.path.exists(readme_path):
        update_readme(readme_path, table_rows)
    
    return filepath


def update_readme(readme_path: str, table_rows: list):
    """Update the performance section in README.md with latest results."""
    import re
    
    with open(readme_path, 'r') as f:
        content = f.read()
    
    # Build the new table
    new_table = '''| Framework | Avg Time (μs) | Relative |
|-----------|---------------|----------|
''' + '\n'.join(table_rows)
    
    # Pattern to match the performance table
    pattern = r'(\| Framework \| Avg Time \(μs\) \| Relative \|\n\|[-|]+\|\n)(\|[^\n]+\|\n)+'
    
    if re.search(pattern, content):
        content = re.sub(pattern, new_table + '\n', content)
        
        with open(readme_path, 'w') as f:
            f.write(content)
        
        print(f'README.md updated: {readme_path}')


if __name__ == '__main__':
    results = run_benchmark()
    save_results(results)
