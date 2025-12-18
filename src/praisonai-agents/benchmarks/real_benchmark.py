#!/usr/bin/env python3
"""
PraisonAI Agents - Real-World Execution Benchmark

Benchmarks actual agent execution with LLM calls across frameworks.
Tests single agent, 2-agent, and 3-agent workflows.

Usage:
    python benchmarks/real_benchmark.py
"""

import time
import statistics
import os
from typing import Literal, List
from dataclasses import dataclass, field
from importlib.metadata import version as get_version

# Ensure API key is set
if not os.environ.get('OPENAI_API_KEY'):
    print("ERROR: OPENAI_API_KEY environment variable not set")
    exit(1)


@dataclass
class ExecutionResult:
    """Execution benchmark results"""
    times: List[float] = field(default_factory=list)
    
    @property
    def avg_time(self) -> float:
        return statistics.mean(self.times) if self.times else 0
    
    @property
    def min_time(self) -> float:
        return min(self.times) if self.times else 0
    
    @property
    def max_time(self) -> float:
        return max(self.times) if self.times else 0
    
    @property
    def std_dev(self) -> float:
        return statistics.stdev(self.times) if len(self.times) > 1 else 0


def get_package_versions():
    """Get version numbers for benchmarked packages."""
    packages = {
        'PraisonAI': 'praisonaiagents',
        'Agno': 'agno',
    }
    versions = {}
    for display_name, pkg_name in packages.items():
        try:
            versions[display_name] = get_version(pkg_name)
        except Exception:
            versions[display_name] = 'not installed'
    return versions


# ============================================================================
# Tool Definitions
# ============================================================================

def get_weather(city: Literal["nyc", "sf"]) -> str:
    """Get weather information for a city."""
    if city == "nyc":
        return "New York: Cloudy, 45°F, 60% humidity"
    return "San Francisco: Sunny, 72°F, 40% humidity"


def get_time(timezone: Literal["est", "pst"]) -> str:
    """Get current time in a timezone."""
    if timezone == "est":
        return "Eastern Time: 2:30 PM"
    return "Pacific Time: 11:30 AM"


def calculate(expression: str) -> str:
    """Calculate a math expression."""
    try:
        result = eval(expression)
        return f"Result: {result}"
    except Exception:
        return "Error: Invalid expression"


# ============================================================================
# PraisonAI Benchmarks
# ============================================================================

def benchmark_praisonai_single(iterations: int = 3) -> ExecutionResult:
    """Benchmark single PraisonAI agent execution."""
    from praisonaiagents import Agent
    
    result = ExecutionResult()
    
    for i in range(iterations):
        print(f"  PraisonAI single agent iteration {i+1}/{iterations}...")
        
        agent = Agent(
            name="Assistant",
            instructions="You are a helpful assistant. Be very brief.",
            llm="gpt-4o-mini",
            tools=[get_weather],
            verbose=False
        )
        
        start = time.perf_counter()
        response = agent.start("What's the weather in NYC? Reply in one sentence.")
        elapsed = time.perf_counter() - start
        
        result.times.append(elapsed)
        print(f"    Time: {elapsed:.2f}s")
    
    return result


def benchmark_praisonai_two_agents(iterations: int = 3) -> ExecutionResult:
    """Benchmark 2 PraisonAI agents working together."""
    from praisonaiagents import Agent, PraisonAIAgents
    
    result = ExecutionResult()
    
    for i in range(iterations):
        print(f"  PraisonAI 2-agent iteration {i+1}/{iterations}...")
        
        researcher = Agent(
            name="Researcher",
            role="Research Assistant",
            goal="Gather weather information",
            instructions="Get weather data and pass to reporter. Be brief.",
            llm="gpt-4o-mini",
            tools=[get_weather],
            verbose=False
        )
        
        reporter = Agent(
            name="Reporter",
            role="News Reporter",
            goal="Create weather report",
            instructions="Create a one-sentence weather summary.",
            llm="gpt-4o-mini",
            verbose=False
        )
        
        agents = PraisonAIAgents(
            agents=[researcher, reporter],
            process="sequential",
            verbose=False
        )
        
        start = time.perf_counter()
        response = agents.start("Get NYC weather and create a brief report.")
        elapsed = time.perf_counter() - start
        
        result.times.append(elapsed)
        print(f"    Time: {elapsed:.2f}s")
    
    return result


def benchmark_praisonai_three_agents(iterations: int = 3) -> ExecutionResult:
    """Benchmark 3 PraisonAI agents working together."""
    from praisonaiagents import Agent, PraisonAIAgents
    
    result = ExecutionResult()
    
    for i in range(iterations):
        print(f"  PraisonAI 3-agent iteration {i+1}/{iterations}...")
        
        weather_agent = Agent(
            name="WeatherAgent",
            role="Weather Specialist",
            goal="Get weather data",
            instructions="Fetch weather information. Be brief.",
            llm="gpt-4o-mini",
            tools=[get_weather],
            verbose=False
        )
        
        time_agent = Agent(
            name="TimeAgent",
            role="Time Specialist",
            goal="Get time information",
            instructions="Fetch timezone information. Be brief.",
            llm="gpt-4o-mini",
            tools=[get_time],
            verbose=False
        )
        
        summarizer = Agent(
            name="Summarizer",
            role="Summary Writer",
            goal="Combine information",
            instructions="Create a one-sentence summary combining weather and time.",
            llm="gpt-4o-mini",
            verbose=False
        )
        
        agents = PraisonAIAgents(
            agents=[weather_agent, time_agent, summarizer],
            process="sequential",
            verbose=False
        )
        
        start = time.perf_counter()
        response = agents.start("Get NYC weather and EST time, then summarize.")
        elapsed = time.perf_counter() - start
        
        result.times.append(elapsed)
        print(f"    Time: {elapsed:.2f}s")
    
    return result


# ============================================================================
# Agno Benchmarks
# ============================================================================

def benchmark_agno_single(iterations: int = 3) -> ExecutionResult:
    """Benchmark single Agno agent execution."""
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    
    result = ExecutionResult()
    
    for i in range(iterations):
        print(f"  Agno single agent iteration {i+1}/{iterations}...")
        
        agent = Agent(
            model=OpenAIChat(id="gpt-4o-mini"),
            instructions=["You are a helpful assistant. Be very brief."],
            tools=[get_weather],
        )
        
        start = time.perf_counter()
        response = agent.run("What's the weather in NYC? Reply in one sentence.")
        elapsed = time.perf_counter() - start
        
        result.times.append(elapsed)
        print(f"    Time: {elapsed:.2f}s")
    
    return result


def benchmark_agno_two_agents(iterations: int = 3) -> ExecutionResult:
    """Benchmark 2 Agno agents working together (using Team)."""
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.team import Team
    
    result = ExecutionResult()
    
    for i in range(iterations):
        print(f"  Agno 2-agent iteration {i+1}/{iterations}...")
        
        researcher = Agent(
            name="Researcher",
            model=OpenAIChat(id="gpt-4o-mini"),
            instructions=["Get weather data. Be brief."],
            tools=[get_weather],
        )
        
        reporter = Agent(
            name="Reporter",
            model=OpenAIChat(id="gpt-4o-mini"),
            instructions=["Create a one-sentence weather summary."],
        )
        
        team = Team(
            members=[researcher, reporter],
            model=OpenAIChat(id="gpt-4o-mini"),
        )
        
        start = time.perf_counter()
        response = team.run("Get NYC weather and create a brief report.")
        elapsed = time.perf_counter() - start
        
        result.times.append(elapsed)
        print(f"    Time: {elapsed:.2f}s")
    
    return result


def benchmark_agno_three_agents(iterations: int = 3) -> ExecutionResult:
    """Benchmark 3 Agno agents working together."""
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.team import Team
    
    result = ExecutionResult()
    
    for i in range(iterations):
        print(f"  Agno 3-agent iteration {i+1}/{iterations}...")
        
        weather_agent = Agent(
            name="WeatherAgent",
            model=OpenAIChat(id="gpt-4o-mini"),
            instructions=["Fetch weather information. Be brief."],
            tools=[get_weather],
        )
        
        time_agent = Agent(
            name="TimeAgent",
            model=OpenAIChat(id="gpt-4o-mini"),
            instructions=["Fetch timezone information. Be brief."],
            tools=[get_time],
        )
        
        summarizer = Agent(
            name="Summarizer",
            model=OpenAIChat(id="gpt-4o-mini"),
            instructions=["Create a one-sentence summary combining weather and time."],
        )
        
        team = Team(
            members=[weather_agent, time_agent, summarizer],
            model=OpenAIChat(id="gpt-4o-mini"),
        )
        
        start = time.perf_counter()
        response = team.run("Get NYC weather and EST time, then summarize.")
        elapsed = time.perf_counter() - start
        
        result.times.append(elapsed)
        print(f"    Time: {elapsed:.2f}s")
    
    return result


# ============================================================================
# Save Results
# ============================================================================

def save_results(results: dict, versions: dict):
    """Save benchmark results to file."""
    import os
    from datetime import datetime
    
    filepath = os.path.join(os.path.dirname(__file__), 'REAL_BENCHMARK_RESULTS.md')
    
    with open(filepath, 'w') as f:
        f.write('# PraisonAI Agents - Real-World Execution Benchmark\n\n')
        f.write(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write('**Model:** gpt-4o-mini\n')
        f.write('**Iterations:** 3 per test\n\n')
        
        f.write('## Results Summary\n\n')
        f.write('| Test | PraisonAI (avg) | Agno (avg) | Difference |\n')
        f.write('|------|-----------------|------------|------------|\n')
        
        tests = ['single', 'two_agents', 'three_agents']
        test_names = ['Single Agent', '2 Agents', '3 Agents']
        
        for test, name in zip(tests, test_names):
            praison_key = f'praisonai_{test}'
            agno_key = f'agno_{test}'
            
            if praison_key in results and agno_key in results:
                praison_avg = results[praison_key].avg_time
                agno_avg = results[agno_key].avg_time
                
                if praison_avg < agno_avg:
                    diff = f'PraisonAI {agno_avg/praison_avg:.2f}x faster'
                else:
                    diff = f'Agno {praison_avg/agno_avg:.2f}x faster'
                
                f.write(f'| {name} | {praison_avg:.2f}s | {agno_avg:.2f}s | {diff} |\n')
        
        f.write('\n## Detailed Results\n\n')
        
        for key, result in results.items():
            f.write(f'### {key}\n')
            f.write(f'- Average: {result.avg_time:.2f}s\n')
            f.write(f'- Min: {result.min_time:.2f}s\n')
            f.write(f'- Max: {result.max_time:.2f}s\n')
            f.write(f'- Std Dev: {result.std_dev:.2f}s\n')
            f.write(f'- Times: {[f"{t:.2f}s" for t in result.times]}\n\n')
        
        f.write('## Package Versions\n\n')
        f.write('| Package | Version |\n')
        f.write('|---------|--------|\n')
        for pkg, ver in versions.items():
            f.write(f'| {pkg} | {ver} |\n')
        
        f.write('\n## How to Reproduce\n\n')
        f.write('```bash\n')
        f.write('export OPENAI_API_KEY=your_key\n')
        f.write('cd praisonai-agents\n')
        f.write('python benchmarks/real_benchmark.py\n')
        f.write('```\n')
    
    print(f'\nResults saved to: {filepath}')


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("PraisonAI Agents - Real-World Execution Benchmark")
    print("="*70)
    print("\nThis benchmark measures actual agent execution time including:")
    print("  - LLM API calls")
    print("  - Tool execution")
    print("  - Multi-agent coordination")
    print("\nModel: gpt-4o-mini")
    print("Iterations: 3 per test")
    
    versions = get_package_versions()
    print(f"\nPackage versions:")
    for pkg, ver in versions.items():
        print(f"  {pkg}: {ver}")
    
    results = {}
    
    # Single Agent Tests
    print("\n" + "="*70)
    print("SINGLE AGENT BENCHMARK")
    print("="*70)
    
    print("\nTesting PraisonAI single agent...")
    results['praisonai_single'] = benchmark_praisonai_single()
    
    print("\nTesting Agno single agent...")
    results['agno_single'] = benchmark_agno_single()
    
    # 2-Agent Tests
    print("\n" + "="*70)
    print("2-AGENT BENCHMARK")
    print("="*70)
    
    print("\nTesting PraisonAI 2 agents...")
    results['praisonai_two_agents'] = benchmark_praisonai_two_agents()
    
    print("\nTesting Agno 2 agents (Team)...")
    results['agno_two_agents'] = benchmark_agno_two_agents()
    
    # 3-Agent Tests
    print("\n" + "="*70)
    print("3-AGENT BENCHMARK")
    print("="*70)
    
    print("\nTesting PraisonAI 3 agents...")
    results['praisonai_three_agents'] = benchmark_praisonai_three_agents()
    
    print("\nTesting Agno 3 agents (Team)...")
    results['agno_three_agents'] = benchmark_agno_three_agents()
    
    # Summary
    print("\n" + "="*70)
    print("RESULTS SUMMARY")
    print("="*70)
    
    print(f"\n{'Test':<20} {'PraisonAI (avg)':<18} {'Agno (avg)':<15} {'Difference':<20}")
    print("-" * 73)
    
    tests = [
        ('Single Agent', 'praisonai_single', 'agno_single'),
        ('2 Agents', 'praisonai_two_agents', 'agno_two_agents'),
        ('3 Agents', 'praisonai_three_agents', 'agno_three_agents'),
    ]
    
    for name, praison_key, agno_key in tests:
        praison_avg = results[praison_key].avg_time
        agno_avg = results[agno_key].avg_time
        
        if praison_avg < agno_avg:
            diff = f'PraisonAI {agno_avg/praison_avg:.2f}x faster'
        else:
            diff = f'Agno {praison_avg/agno_avg:.2f}x faster'
        
        print(f"{name:<20} {praison_avg:<18.2f}s {agno_avg:<15.2f}s {diff:<20}")
    
    print("\n" + "="*70)
    
    # Save results
    save_results(results, versions)
