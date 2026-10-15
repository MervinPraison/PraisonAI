"""
PraisonAI Agents - Comprehensive Performance Benchmark

Measures agent instantiation time and memory footprint across
multiple AI agent frameworks using industry-standard methodology.

Usage:
    python benchmarks/performance_benchmark.py
    python benchmarks/performance_benchmark.py --save          # rewrite BENCHMARK_RESULTS.md
    python benchmarks/performance_benchmark.py --only praisonai
"""

import gc
import time
import tracemalloc
import statistics
from typing import Literal, List, Callable
from dataclasses import dataclass, field
import argparse


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
# Framework factories
#
# Each builder imports its framework lazily and returns a zero-arg callable
# that creates one agent with one tool. A missing framework raises ImportError
# and is skipped, so the script runs with only praisonaiagents installed.
# ============================================================================

INSTRUCTIONS = "Be concise, reply with one sentence."


def get_weather(city: Literal["nyc", "sf"]):
    """Use this to get weather information."""
    if city == "nyc":
        return "It might be cloudy in nyc"
    elif city == "sf":
        return "It's always sunny in sf"


tools = [get_weather]


def build_praisonai():
    from praisonaiagents import Agent as PraisonAgent
    return lambda: PraisonAgent(
        name="Test Agent", instructions=INSTRUCTIONS, model="gpt-4o-mini",
        tools=tools, output="silent",
    )


def build_praisonai_litellm():
    from praisonaiagents import Agent as PraisonAgent
    return lambda: PraisonAgent(
        name="Test Agent", instructions=INSTRUCTIONS, model="openai/gpt-4o-mini",
        tools=tools, output="silent",
    )


def build_agno():
    from agno.agent import Agent as AgnoAgent
    from agno.models.openai import OpenAIChat
    return lambda: AgnoAgent(model=OpenAIChat(id="gpt-4o-mini"), instructions=INSTRUCTIONS, tools=tools)


def build_pydantic():
    from pydantic_ai import Agent as PydanticAgent

    def create():
        agent = PydanticAgent("openai:gpt-4o-mini", system_prompt=INSTRUCTIONS)
        agent.tool_plain(get_weather)
        return agent
    return create


def build_openai_agents():
    from agents import Agent as OpenAIAgent, function_tool
    return lambda: OpenAIAgent(
        name="Test agent", instructions=INSTRUCTIONS, model="gpt-4o-mini",
        tools=[function_tool(get_weather)],
    )


def build_langgraph():
    from langchain_core.tools import tool as langchain_tool
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent
    return lambda: create_react_agent(
        model=ChatOpenAI(model="gpt-4o-mini"), tools=[langchain_tool(get_weather)],
    )


def build_crewai():
    from crewai.agent import Agent as CrewAgent
    from crewai.tools import tool as crewai_tool

    def create():
        return CrewAgent(
            llm="gpt-4o-mini", role="Test Agent", goal=INSTRUCTIONS,
            tools=[crewai_tool("Weather Tool")(get_weather)], backstory="Test",
        )
    return create


# key -> (display name, PyPI package, builder)
FRAMEWORKS = {
    'praisonai': ('PraisonAI', 'praisonaiagents', build_praisonai),
    'praisonai_litellm': ('PraisonAI (LiteLLM)', 'praisonaiagents', build_praisonai_litellm),
    'agno': ('Agno', 'agno', build_agno),
    'pydantic': ('PydanticAI', 'pydantic-ai-slim', build_pydantic),
    'openai_agents': ('OpenAI Agents SDK', 'openai-agents', build_openai_agents),
    'langgraph': ('LangGraph', 'langgraph', build_langgraph),
    'crewai': ('CrewAI', 'crewai', build_crewai),
}


def get_package_versions(keys=None):
    """Get version numbers for benchmarked packages."""
    from importlib.metadata import version as get_version

    versions = {}
    for key in keys or FRAMEWORKS:
        display_name, pkg_name, _ = FRAMEWORKS[key]
        if pkg_name in versions:
            continue
        try:
            versions[pkg_name] = get_version(pkg_name)
        except Exception:
            versions[pkg_name] = 'not installed'
    return versions


def get_machine_info() -> dict:
    """Describe the machine so results are traceable."""
    import os
    import platform

    load = os.getloadavg()[0] if hasattr(os, 'getloadavg') else None
    return {
        'Platform': platform.platform(),
        'Processor': platform.processor() or platform.machine(),
        'CPUs': os.cpu_count(),
        'Python': platform.python_version(),
        'Load avg (1 min) at start': f'{load:.2f}' if load is not None else 'n/a',
    }


def rank_results(results: dict) -> list:
    """Return ``(key, result, ratio)`` sorted fastest first, ratio vs the fastest."""
    ranked = sorted(results.items(), key=lambda x: x[1].avg_run_time)
    fastest = ranked[0][1].avg_run_time if ranked else 0
    return [(k, r, r.avg_run_time / fastest if fastest > 0 else 0) for k, r in ranked]


def save_benchmark_results(results: dict, machine: dict, iterations: int, warmup: int,
                           filename: str = 'BENCHMARK_RESULTS.md') -> str:
    """Write every framework's results from this single run to ``BENCHMARK_RESULTS.md``."""
    import os
    from datetime import datetime

    filepath = os.path.join(os.path.dirname(__file__), filename)
    versions = get_package_versions(results.keys())

    def us(seconds):
        value = seconds * 1e6
        return f'{value:,.2f}' if value >= 1000 else f'{value:.2f}'

    lines = [
        '# PraisonAI Agents - Benchmark Results', '',
        f'**Generated:** {datetime.now().strftime("%Y-%m-%d")} (single run of `performance_benchmark.py`)',
        f'**Methodology:** {warmup} warmup runs + {iterations} measured iterations per framework',
        f'**Setup (every framework):** one agent, model `gpt-4o-mini`, one `get_weather` tool, '
        'no LLM call. Tool wrapping (`function_tool`, `@tool`, ...) happens inside the timed call. '
        'Frameworks that were not installed are omitted.',
        '', '## Agent Instantiation Time', '',
        '| Framework | Avg (μs) | Min (μs) | Median (μs) | Std (μs) | Avg memory (KiB) | Relative |',
        '|-----------|----------|----------|-------------|----------|------------------|----------|',
    ]
    for rank, (key, r, ratio) in enumerate(rank_results(results)):
        relative = '1.00x (fastest)' if rank == 0 else (f'{ratio:,.0f}x' if ratio >= 100 else f'{ratio:.2f}x')
        lines.append(
            f'| {FRAMEWORKS[key][0]} | {us(r.avg_run_time)} | {us(r.min_run_time)} | '
            f'{us(r.median_run_time)} | {us(r.std_dev_run_time)} | '
            f'{r.avg_memory_usage * 1024:.2f} | {relative} |'
        )
    lines += ['', '## Package Versions', '', '| Package | Version |', '|---------|---------|']
    lines += [f'| {pkg} | {ver} |' for pkg, ver in versions.items()]
    lines += ['', '## Machine', '', '| Field | Value |', '|-------|-------|']
    lines += [f'| {k} | {v} |' for k, v in machine.items()]
    lines += [
        '', '## How to Reproduce', '', '```bash', 'cd src/praisonai-agents',
        'pip install -e . agno openai-agents "pydantic-ai-slim[openai]" langgraph langchain-openai crewai',
        "# OpenAI-backed constructors need a key to exist; no request is made",
        "OPENAI_API_KEY=sk-dummy PYTHONWARNINGS='ignore::DeprecationWarning' python benchmarks/performance_benchmark.py --save",
        '```', '',
        'Older, superseded result files live in [`archive/`](archive/).', '',
    ]
    with open(filepath, 'w') as f:
        f.write('\n'.join(lines))

    print(f'\nResults saved to: {filepath}')
    return filepath


def main():
    parser = argparse.ArgumentParser(description='PraisonAI Agents - Comprehensive Performance Benchmark')
    parser.add_argument('--save', action='store_true', help='Save results to BENCHMARK_RESULTS.md')
    parser.add_argument('--iterations', type=int, default=1000, help='Measured iterations (default: 1000)')
    parser.add_argument('--warmup', type=int, default=10, help='Warmup runs (default: 10)')
    parser.add_argument('--only', nargs='+', choices=list(FRAMEWORKS), help='Benchmark only these frameworks')
    args = parser.parse_args()

    machine = get_machine_info()

    print("="*70)
    print("PraisonAI Agents - Comprehensive Performance Benchmark")
    print("="*70)
    print("\nThis benchmark measures:")
    print("  1. Agent instantiation time (how fast an agent object is created)")
    print("  2. Memory footprint (how much memory an agent uses)")
    print("\nMethodology:")
    print(f"  - {args.warmup} warmup runs (not measured)")
    print(f"  - {args.iterations} measured iterations")
    print("  - tracemalloc for memory measurement")
    print("  - Baseline subtraction for accuracy")
    print("\nMachine:")
    for k, v in machine.items():
        print(f"  - {k}: {v}")

    results = {}
    for key in args.only or FRAMEWORKS:
        display_name, _, builder = FRAMEWORKS[key]
        try:
            create = builder()
        except ImportError:
            print(f"\nSkipping {display_name}: not installed")
            continue
        try:
            results[key] = run_benchmark(create, display_name, iterations=args.iterations, warmup=args.warmup)
        except Exception as e:
            print(f"Error testing {display_name}: {e}")

    if not results:
        print("\nNo framework could be benchmarked.")
        return 1

    # Final Comparison Table
    print("\n" + "="*70)
    print("RESULTS SUMMARY")
    print("="*70)
    print(f"\n{'Framework':<25} {'Avg Time (μs)':<15} {'Median (μs)':<13} {'Avg Memory (KiB)':<18} {'Relative':<15}")
    print("-" * 86)
    for key, result, ratio in rank_results(results):
        print(f"{FRAMEWORKS[key][0]:<25} {result.avg_run_time*1e6:<15.2f} {result.median_run_time*1e6:<13.2f} "
              f"{result.avg_memory_usage*1024:<18.2f} {ratio:.2f}x")
    print("\n" + "="*70)

    if args.save:
        save_benchmark_results(results, machine, args.iterations, args.warmup)
    else:
        print('\nResults not saved (use --save flag to save results to file)')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
