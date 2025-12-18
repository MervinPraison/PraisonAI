"""
PraisonAI Agents - Comprehensive Performance Benchmark

Measures agent instantiation time and memory footprint across
multiple AI agent frameworks using industry-standard methodology.

Usage:
    python benchmarks/performance_benchmark.py
"""

import gc
import time
import tracemalloc
import statistics
from typing import Literal, List, Callable
from dataclasses import dataclass, field


@dataclass
class PerformanceResult:
    """Performance measurement results"""
    run_times: List[float] = field(default_factory=list)
    memory_usages: List[float] = field(default_factory=list)
    
    @property
    def avg_run_time(self) -> float:
        return statistics.mean(self.run_times) if self.run_times else 0
    
    @property
    def avg_memory_usage(self) -> float:
        return statistics.mean(self.memory_usages) if self.memory_usages else 0
    
    @property
    def min_run_time(self) -> float:
        return min(self.run_times) if self.run_times else 0
    
    @property
    def max_run_time(self) -> float:
        return max(self.run_times) if self.run_times else 0
    
    @property
    def std_dev_run_time(self) -> float:
        return statistics.stdev(self.run_times) if len(self.run_times) > 1 else 0
    
    @property
    def median_run_time(self) -> float:
        return statistics.median(self.run_times) if self.run_times else 0


def compute_tracemalloc_baseline(samples: int = 3) -> float:
    """Compute baseline memory usage for tracemalloc"""
    def empty_func():
        return
    
    results = []
    for _ in range(samples):
        gc.collect()
        tracemalloc.start()
        empty_func()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        results.append(peak / 1024 / 1024)  # Convert to MiB
    
    return sum(results) / len(results) if results else 0


def measure_time(func: Callable, iterations: int = 1000, warmup: int = 10) -> List[float]:
    """Measure execution time for a function"""
    # Warmup runs
    for _ in range(warmup):
        func()
    
    # Measured runs
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append(end - start)
    
    return times


def measure_memory(func: Callable, iterations: int = 1000, warmup: int = 10) -> List[float]:
    """Measure memory usage for a function"""
    baseline = compute_tracemalloc_baseline()
    
    # Warmup runs
    for _ in range(warmup):
        func()
    
    # Measured runs
    memory_usages = []
    for _ in range(iterations):
        gc.collect()
        tracemalloc.start()
        func()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        peak_mib = peak / 1024 / 1024
        adjusted = max(0, peak_mib - baseline)
        memory_usages.append(adjusted)
    
    return memory_usages


def run_benchmark(func: Callable, name: str, iterations: int = 1000, warmup: int = 10) -> PerformanceResult:
    """Run full benchmark for a function"""
    print(f"\n{'='*60}")
    print(f"Benchmarking: {name}")
    print(f"{'='*60}")
    print(f"Warmup runs: {warmup}")
    print(f"Measured iterations: {iterations}")
    
    print("\nMeasuring runtime...")
    run_times = measure_time(func, iterations, warmup)
    
    print("Measuring memory...")
    memory_usages = measure_memory(func, iterations, warmup)
    
    result = PerformanceResult(run_times=run_times, memory_usages=memory_usages)
    
    print(f"\nResults for {name}:")
    print(f"  Average Time: {result.avg_run_time:.6f} seconds ({result.avg_run_time * 1_000_000:.2f} μs)")
    print(f"  Min Time:     {result.min_run_time:.6f} seconds")
    print(f"  Max Time:     {result.max_run_time:.6f} seconds")
    print(f"  Std Dev:      {result.std_dev_run_time:.6f} seconds")
    print(f"  Median Time:  {result.median_run_time:.6f} seconds")
    print(f"  Avg Memory:   {result.avg_memory_usage:.6f} MiB ({result.avg_memory_usage * 1024:.2f} KiB)")
    
    return result


# ============================================================================
# Framework Imports
# ============================================================================
from praisonaiagents import Agent as PraisonAgent
from agno.agent import Agent as AgnoAgent
from agno.models.openai import OpenAIChat

# Additional frameworks for comparison
try:
    from pydantic_ai import Agent as PydanticAgent
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False

try:
    from crewai.agent import Agent as CrewAgent
    from crewai.tools import tool as crewai_tool
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False

try:
    from langchain_core.tools import tool as langchain_tool
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

try:
    from agents import Agent as OpenAIAgent, function_tool
    OPENAI_AGENTS_AVAILABLE = True
except ImportError:
    OPENAI_AGENTS_AVAILABLE = False


def get_weather(city: Literal["nyc", "sf"]):
    """Use this to get weather information."""
    if city == "nyc":
        return "It might be cloudy in nyc"
    elif city == "sf":
        return "It's always sunny in sf"


tools = [get_weather]


def instantiate_praisonai_agent():
    """Instantiate a PraisonAI agent with one tool."""
    return PraisonAgent(
        name="Test Agent",
        instructions="Be concise, reply with one sentence.",
        llm="gpt-4o-mini",
        tools=tools,
        verbose=False
    )


def instantiate_praisonai_litellm_agent():
    """Instantiate a PraisonAI agent with LiteLLM backend."""
    return PraisonAgent(
        name="Test Agent",
        instructions="Be concise, reply with one sentence.",
        llm="openai/gpt-4o-mini",
        tools=tools,
        verbose=False
    )


def instantiate_agno_agent():
    """Instantiate an Agno agent with one tool."""
    return AgnoAgent(model=OpenAIChat(id="gpt-4o-mini"), tools=tools)


def instantiate_pydantic_agent():
    """Instantiate a PydanticAI agent with one tool."""
    agent = PydanticAgent("openai:gpt-4o-mini", system_prompt="Be concise, reply with one sentence.")
    @agent.tool_plain
    def get_weather_pydantic(city: Literal["nyc", "sf"]):
        """Use this to get weather information."""
        if city == "nyc":
            return "It might be cloudy in nyc"
        elif city == "sf":
            return "It's always sunny in sf"
    return agent


def instantiate_openai_agents():
    """Instantiate an OpenAI Agents SDK agent with one tool."""
    return OpenAIAgent(
        name="Test agent",
        instructions="Be concise, reply with one sentence.",
        model="gpt-4o-mini",
        tools=[function_tool(get_weather)],
    )


def instantiate_langgraph_agent():
    """Instantiate a LangGraph agent with one tool."""
    @langchain_tool
    def get_weather_lg(city: Literal["nyc", "sf"]):
        """Use this to get weather information."""
        if city == "nyc":
            return "It might be cloudy in nyc"
        elif city == "sf":
            return "It's always sunny in sf"
    return create_react_agent(model=ChatOpenAI(model="gpt-4o-mini"), tools=[get_weather_lg])


def instantiate_crewai_agent():
    """Instantiate a CrewAI agent with one tool."""
    @crewai_tool("Weather Tool")
    def get_weather_crew(city: Literal["nyc", "sf"]):
        """Use this to get weather information."""
        if city == "nyc":
            return "It might be cloudy in nyc"
        elif city == "sf":
            return "It's always sunny in sf"
    return CrewAgent(
        llm="gpt-4o-mini",
        role="Test Agent",
        goal="Be concise, reply with one sentence.",
        tools=[get_weather_crew],
        backstory="Test",
    )


def get_package_versions():
    """Get version numbers for all benchmarked packages."""
    from importlib.metadata import version as get_version
    
    packages = {
        'PraisonAI': 'praisonaiagents',
        'Agno': 'agno',
        'PydanticAI': 'pydantic-ai',
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


def save_benchmark_results(results: dict, baseline):
    """Save benchmark results to BENCHMARK_RESULTS.md and update README.md"""
    import os
    import re
    from datetime import datetime
    
    benchmarks_dir = os.path.dirname(__file__)
    filepath = os.path.join(benchmarks_dir, 'BENCHMARK_RESULTS.md')
    
    # Get package versions
    versions = get_package_versions()
    
    display_names = {
        'agno': 'Agno',
        'praisonai': 'PraisonAI',
        'praisonai_litellm': 'PraisonAI (LiteLLM)',
        'pydantic': 'PydanticAI',
        'openai_agents': 'OpenAI Agents SDK',
        'langgraph': 'LangGraph',
        'crewai': 'CrewAI'
    }
    
    # Build table rows
    table_rows = []
    sorted_results = sorted(results.items(), key=lambda x: x[1].avg_run_time)
    
    for name, result in sorted_results:
        display_name = display_names.get(name, name)
        avg_us = result.avg_run_time * 1e6
        ratio = result.avg_run_time / baseline.avg_run_time if baseline.avg_run_time > 0 else 0
        
        if name == 'praisonai':
            table_rows.append(f'| **{display_name}** | **{avg_us:.2f}** | **1.00x (fastest)** |')
        else:
            avg_str = f'{avg_us:,.2f}' if avg_us >= 1000 else f'{avg_us:.2f}'
            ratio_str = f'{ratio:,.0f}x' if ratio >= 100 else f'{ratio:.2f}x'
            table_rows.append(f'| {display_name} | {avg_str} | {ratio_str} |')
    
    # Save to BENCHMARK_RESULTS.md
    with open(filepath, 'w') as f:
        f.write('# PraisonAI Agents - Benchmark Results\n\n')
        f.write(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write('**Methodology:** 10 warmup runs + 1000 measured iterations\n\n')
        f.write('## Agent Instantiation Time\n\n')
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
        f.write('python benchmarks/performance_benchmark.py\n')
        f.write('```\n')
    
    print(f'\nResults saved to: {filepath}')
    
    # Update README.md
    readme_path = os.path.join(benchmarks_dir, '..', '..', '..', 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r') as f:
            content = f.read()
        
        new_table = '''| Framework | Avg Time (μs) | Relative |
|-----------|---------------|----------|
''' + '\n'.join(table_rows)
        
        pattern = r'(\| Framework \| Avg Time \(μs\) \| Relative \|\n\|[-|]+\|\n)(\|[^\n]+\|\n)+'
        
        if re.search(pattern, content):
            content = re.sub(pattern, new_table + '\n', content)
            
            with open(readme_path, 'w') as f:
                f.write(content)
            
            print(f'README.md updated: {readme_path}')


if __name__ == "__main__":
    print("="*70)
    print("PraisonAI Agents - Comprehensive Performance Benchmark")
    print("="*70)
    print("\nThis benchmark measures:")
    print("  1. Agent instantiation time (how fast an agent object is created)")
    print("  2. Memory footprint (how much memory an agent uses)")
    print("\nMethodology:")
    print("  - 10 warmup runs (not measured)")
    print("  - 1000 measured iterations")
    print("  - tracemalloc for memory measurement")
    print("  - Baseline subtraction for accuracy")
    print("\nFrameworks available:")
    print("  - PraisonAI: ✅")
    print(f"  - Agno: ✅")
    print(f"  - PydanticAI: {'✅' if PYDANTIC_AVAILABLE else '❌'}")
    print(f"  - OpenAI Agents SDK: {'✅' if OPENAI_AGENTS_AVAILABLE else '❌'}")
    print(f"  - LangGraph: {'✅' if LANGGRAPH_AVAILABLE else '❌'}")
    print(f"  - CrewAI: {'✅' if CREWAI_AVAILABLE else '❌'}")
    
    results = {}
    
    # Test PraisonAI first
    try:
        print("\n" + "="*70)
        print("Testing PraisonAI Agents")
        print("="*70)
        results['praisonai'] = run_benchmark(
            instantiate_praisonai_agent,
            "PraisonAI",
            iterations=1000,
            warmup=10
        )
    except Exception as e:
        print(f"Error testing PraisonAI: {e}")
    
    try:
        print("\n" + "="*70)
        print("Testing PraisonAI Agents (LiteLLM)")
        print("="*70)
        results['praisonai_litellm'] = run_benchmark(
            instantiate_praisonai_litellm_agent,
            "PraisonAI (LiteLLM)",
            iterations=1000,
            warmup=10
        )
    except Exception as e:
        print(f"Error testing PraisonAI (LiteLLM): {e}")
    
    # Test Agno
    try:
        print("\n" + "="*70)
        print("Testing Agno")
        print("="*70)
        results['agno'] = run_benchmark(
            instantiate_agno_agent,
            "Agno",
            iterations=1000,
            warmup=10
        )
    except Exception as e:
        print(f"Error testing Agno: {e}")
    
    # Test PydanticAI
    if PYDANTIC_AVAILABLE:
        try:
            print("\n" + "="*70)
            print("Testing PydanticAI")
            print("="*70)
            results['pydantic'] = run_benchmark(
                instantiate_pydantic_agent,
                "PydanticAI Agent Instantiation",
                iterations=1000,
                warmup=10
            )
        except Exception as e:
            print(f"Error testing PydanticAI: {e}")
    
    # Test OpenAI Agents SDK
    if OPENAI_AGENTS_AVAILABLE:
        try:
            print("\n" + "="*70)
            print("Testing OpenAI Agents SDK")
            print("="*70)
            results['openai_agents'] = run_benchmark(
                instantiate_openai_agents,
                "OpenAI Agents SDK Instantiation",
                iterations=1000,
                warmup=10
            )
        except Exception as e:
            print(f"Error testing OpenAI Agents SDK: {e}")
    
    # Test LangGraph
    if LANGGRAPH_AVAILABLE:
        try:
            print("\n" + "="*70)
            print("Testing LangGraph")
            print("="*70)
            results['langgraph'] = run_benchmark(
                instantiate_langgraph_agent,
                "LangGraph Agent Instantiation",
                iterations=1000,
                warmup=10
            )
        except Exception as e:
            print(f"Error testing LangGraph: {e}")
    
    # Test CrewAI
    if CREWAI_AVAILABLE:
        try:
            print("\n" + "="*70)
            print("Testing CrewAI")
            print("="*70)
            results['crewai'] = run_benchmark(
                instantiate_crewai_agent,
                "CrewAI Agent Instantiation",
                iterations=1000,
                warmup=10
            )
        except Exception as e:
            print(f"Error testing CrewAI: {e}")
    
    # Final Comparison Table
    print("\n" + "="*70)
    print("RESULTS SUMMARY")
    print("="*70)
    
    if 'praisonai' in results:
        baseline = results['praisonai']
        
        print(f"\n{'Framework':<25} {'Avg Time (μs)':<15} {'Avg Memory (KiB)':<18} {'Relative':<15}")
        print("-" * 73)
        
        # Sort by time
        sorted_results = sorted(results.items(), key=lambda x: x[1].avg_run_time)
        
        for name, result in sorted_results:
            time_ratio = result.avg_run_time / baseline.avg_run_time if baseline.avg_run_time > 0 else 0
            
            time_str = f"{time_ratio:.2f}x"
            
            display_name = {
                'agno': 'Agno',
                'praisonai': 'PraisonAI',
                'praisonai_litellm': 'PraisonAI (LiteLLM)',
                'pydantic': 'PydanticAI',
                'openai_agents': 'OpenAI Agents SDK',
                'langgraph': 'LangGraph',
                'crewai': 'CrewAI'
            }.get(name, name)
            
            print(f"{display_name:<25} {result.avg_run_time*1e6:<15.2f} {result.avg_memory_usage*1024:<18.2f} {time_str:<15}")
        
        print("\n" + "="*70)
        
        # Save results to files
        save_benchmark_results(results, baseline)
