#!/usr/bin/env python3
"""
PraisonAI Agents - Detailed Profiling Benchmark

Provides function-level profiling for PraisonAI agent execution.
Shows exactly which functions are called, from which files, and how long each takes.

Usage:
    export OPENAI_API_KEY=your_key
    python benchmarks/detailed_profiling_benchmark.py
    python benchmarks/detailed_profiling_benchmark.py --framework praisonai
    python benchmarks/detailed_profiling_benchmark.py --framework agno
"""

import time
import os
import sys
import argparse
import cProfile
import pstats
import io
from functools import wraps
from collections import defaultdict
from datetime import datetime

# Defaults
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_PROMPT = "What is 2+2? Reply with just the number."


class DetailedProfiler:
    """Detailed function-level profiler with file path tracking."""
    
    def __init__(self):
        self.call_times = defaultdict(list)
        self.call_counts = defaultdict(int)
        self.profiler = None
        
    def start(self):
        """Start cProfile profiler."""
        self.profiler = cProfile.Profile()
        self.profiler.enable()
        
    def stop(self):
        """Stop profiler and return stats."""
        if self.profiler:
            self.profiler.disable()
            return self.profiler
        return None
    
    def get_stats_string(self, sort_by='cumtime', limit=50):
        """Get formatted stats string."""
        if not self.profiler:
            return "No profiler data"
        
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s)
        ps.sort_stats(sort_by)
        ps.print_stats(limit)
        return s.getvalue()
    
    def get_detailed_breakdown(self, filter_pattern=None, limit=100):
        """Get detailed breakdown with file paths."""
        if not self.profiler:
            return []
        
        stats = pstats.Stats(self.profiler)
        
        results = []
        for (filename, line, func), (cc, nc, tt, ct, callers) in stats.stats.items():
            # Filter by pattern if provided
            if filter_pattern and filter_pattern not in filename and filter_pattern not in func:
                continue
            
            results.append({
                'file': filename,
                'line': line,
                'function': func,
                'calls': nc,
                'total_time': tt,
                'cumulative_time': ct,
                'time_per_call': tt / nc if nc > 0 else 0,
            })
        
        # Sort by cumulative time
        results.sort(key=lambda x: x['cumulative_time'], reverse=True)
        return results[:limit]


def profile_praisonai_detailed(model, prompt):
    """Profile PraisonAI agent execution in detail."""
    print("\n" + "=" * 80)
    print("DETAILED PROFILING: PraisonAI")
    print("=" * 80)
    
    profiler = DetailedProfiler()
    
    # Profile import
    print("\n--- Import Phase ---")
    import_start = time.perf_counter()
    profiler.start()
    from praisonaiagents import Agent
    profiler.stop()
    import_time = time.perf_counter() - import_start
    print(f"Import time: {import_time*1000:.2f}ms")
    
    # Show import profile
    print("\nTop 20 functions during import (by cumulative time):")
    print("-" * 80)
    breakdown = profiler.get_detailed_breakdown(filter_pattern='praisonai', limit=20)
    print(f"{'Function':<40} {'File':<50} {'Calls':>8} {'CumTime':>10}")
    print("-" * 80)
    for item in breakdown:
        func = item['function'][:38]
        file = item['file'].split('/')[-1][:48] if '/' in item['file'] else item['file'][:48]
        print(f"{func:<40} {file:<50} {item['calls']:>8} {item['cumulative_time']*1000:>9.2f}ms")
    
    # Profile instantiation
    print("\n--- Instantiation Phase ---")
    profiler2 = DetailedProfiler()
    inst_start = time.perf_counter()
    profiler2.start()
    agent = Agent(
        name="Calculator",
        instructions="You are a helpful assistant. Be very brief.",
        llm=model
    )
    profiler2.stop()
    inst_time = time.perf_counter() - inst_start
    print(f"Instantiation time: {inst_time*1000:.2f}ms")
    
    print("\nTop 30 functions during instantiation (by cumulative time):")
    print("-" * 80)
    breakdown = profiler2.get_detailed_breakdown(filter_pattern='praisonai', limit=30)
    print(f"{'Function':<40} {'File':<50} {'Calls':>8} {'CumTime':>10}")
    print("-" * 80)
    for item in breakdown:
        func = item['function'][:38]
        file = item['file'].split('/')[-1][:48] if '/' in item['file'] else item['file'][:48]
        print(f"{func:<40} {file:<50} {item['calls']:>8} {item['cumulative_time']*1000:>9.2f}ms")
    
    # Profile execution
    print("\n--- Execution Phase (agent.start) ---")
    profiler3 = DetailedProfiler()
    exec_start = time.perf_counter()
    profiler3.start()
    response = agent.start(prompt, output="silent")
    profiler3.stop()
    exec_time = time.perf_counter() - exec_start
    print(f"Execution time: {exec_time*1000:.2f}ms ({exec_time:.2f}s)")
    print(f"Response: {str(response)[:100]}")
    
    print("\nTop 50 functions during execution (by cumulative time):")
    print("-" * 80)
    breakdown = profiler3.get_detailed_breakdown(limit=50)
    print(f"{'Function':<40} {'File':<50} {'Calls':>8} {'CumTime':>10}")
    print("-" * 80)
    for item in breakdown:
        func = item['function'][:38]
        file = item['file'].split('/')[-1][:48] if '/' in item['file'] else item['file'][:48]
        print(f"{func:<40} {file:<50} {item['calls']:>8} {item['cumulative_time']*1000:>9.2f}ms")
    
    # PraisonAI-specific functions
    print("\n--- PraisonAI-Specific Functions ---")
    print("-" * 80)
    praisonai_funcs = profiler3.get_detailed_breakdown(filter_pattern='praisonai', limit=50)
    print(f"{'Function':<40} {'File':<50} {'Calls':>8} {'CumTime':>10}")
    print("-" * 80)
    for item in praisonai_funcs:
        func = item['function'][:38]
        file = item['file'].split('/')[-1][:48] if '/' in item['file'] else item['file'][:48]
        print(f"{func:<40} {file:<50} {item['calls']:>8} {item['cumulative_time']*1000:>9.2f}ms")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY: PraisonAI")
    print("=" * 80)
    print(f"Import time:        {import_time*1000:>10.2f}ms")
    print(f"Instantiation time: {inst_time*1000:>10.2f}ms")
    print(f"Execution time:     {exec_time*1000:>10.2f}ms")
    print(f"Total time:         {(import_time+inst_time+exec_time)*1000:>10.2f}ms")
    
    return {
        'import_time': import_time,
        'instantiation_time': inst_time,
        'execution_time': exec_time,
        'total_time': import_time + inst_time + exec_time,
    }


def profile_agno_detailed(model, prompt):
    """Profile Agno agent execution in detail."""
    print("\n" + "=" * 80)
    print("DETAILED PROFILING: Agno")
    print("=" * 80)
    
    profiler = DetailedProfiler()
    
    # Profile import
    print("\n--- Import Phase ---")
    import_start = time.perf_counter()
    profiler.start()
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    profiler.stop()
    import_time = time.perf_counter() - import_start
    print(f"Import time: {import_time*1000:.2f}ms")
    
    print("\nTop 20 functions during import (by cumulative time):")
    print("-" * 80)
    breakdown = profiler.get_detailed_breakdown(filter_pattern='agno', limit=20)
    print(f"{'Function':<40} {'File':<50} {'Calls':>8} {'CumTime':>10}")
    print("-" * 80)
    for item in breakdown:
        func = item['function'][:38]
        file = item['file'].split('/')[-1][:48] if '/' in item['file'] else item['file'][:48]
        print(f"{func:<40} {file:<50} {item['calls']:>8} {item['cumulative_time']*1000:>9.2f}ms")
    
    # Profile instantiation
    print("\n--- Instantiation Phase ---")
    profiler2 = DetailedProfiler()
    inst_start = time.perf_counter()
    profiler2.start()
    agent = Agent(
        model=OpenAIChat(id=model),
        instructions=["You are a helpful assistant. Be very brief."],
    )
    profiler2.stop()
    inst_time = time.perf_counter() - inst_start
    print(f"Instantiation time: {inst_time*1000:.2f}ms")
    
    print("\nTop 30 functions during instantiation (by cumulative time):")
    print("-" * 80)
    breakdown = profiler2.get_detailed_breakdown(filter_pattern='agno', limit=30)
    print(f"{'Function':<40} {'File':<50} {'Calls':>8} {'CumTime':>10}")
    print("-" * 80)
    for item in breakdown:
        func = item['function'][:38]
        file = item['file'].split('/')[-1][:48] if '/' in item['file'] else item['file'][:48]
        print(f"{func:<40} {file:<50} {item['calls']:>8} {item['cumulative_time']*1000:>9.2f}ms")
    
    # Profile execution
    print("\n--- Execution Phase (agent.run) ---")
    profiler3 = DetailedProfiler()
    exec_start = time.perf_counter()
    profiler3.start()
    response = agent.run(prompt)
    profiler3.stop()
    exec_time = time.perf_counter() - exec_start
    content = str(response.content)[:100] if hasattr(response, 'content') else str(response)[:100]
    print(f"Execution time: {exec_time*1000:.2f}ms ({exec_time:.2f}s)")
    print(f"Response: {content}")
    
    print("\nTop 50 functions during execution (by cumulative time):")
    print("-" * 80)
    breakdown = profiler3.get_detailed_breakdown(limit=50)
    print(f"{'Function':<40} {'File':<50} {'Calls':>8} {'CumTime':>10}")
    print("-" * 80)
    for item in breakdown:
        func = item['function'][:38]
        file = item['file'].split('/')[-1][:48] if '/' in item['file'] else item['file'][:48]
        print(f"{func:<40} {file:<50} {item['calls']:>8} {item['cumulative_time']*1000:>9.2f}ms")
    
    # Agno-specific functions
    print("\n--- Agno-Specific Functions ---")
    print("-" * 80)
    agno_funcs = profiler3.get_detailed_breakdown(filter_pattern='agno', limit=50)
    print(f"{'Function':<40} {'File':<50} {'Calls':>8} {'CumTime':>10}")
    print("-" * 80)
    for item in agno_funcs:
        func = item['function'][:38]
        file = item['file'].split('/')[-1][:48] if '/' in item['file'] else item['file'][:48]
        print(f"{func:<40} {file:<50} {item['calls']:>8} {item['cumulative_time']*1000:>9.2f}ms")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY: Agno")
    print("=" * 80)
    print(f"Import time:        {import_time*1000:>10.2f}ms")
    print(f"Instantiation time: {inst_time*1000:>10.2f}ms")
    print(f"Execution time:     {exec_time*1000:>10.2f}ms")
    print(f"Total time:         {(import_time+inst_time+exec_time)*1000:>10.2f}ms")
    
    return {
        'import_time': import_time,
        'instantiation_time': inst_time,
        'execution_time': exec_time,
        'total_time': import_time + inst_time + exec_time,
    }


def profile_crewai_detailed(model, prompt):
    """Profile CrewAI agent execution in detail."""
    print("\n" + "=" * 80)
    print("DETAILED PROFILING: CrewAI")
    print("=" * 80)
    
    profiler = DetailedProfiler()
    
    # Profile import
    print("\n--- Import Phase ---")
    import_start = time.perf_counter()
    profiler.start()
    from crewai import Agent, Task, Crew
    profiler.stop()
    import_time = time.perf_counter() - import_start
    print(f"Import time: {import_time*1000:.2f}ms")
    
    # Profile instantiation
    print("\n--- Instantiation Phase ---")
    profiler2 = DetailedProfiler()
    inst_start = time.perf_counter()
    profiler2.start()
    agent = Agent(
        role="Calculator",
        goal="Answer math questions",
        backstory="You are a helpful assistant.",
        llm=model,
        verbose=False
    )
    task = Task(
        description=prompt,
        expected_output="A number",
        agent=agent
    )
    crew = Crew(
        agents=[agent],
        tasks=[task],
        verbose=False
    )
    profiler2.stop()
    inst_time = time.perf_counter() - inst_start
    print(f"Instantiation time: {inst_time*1000:.2f}ms")
    
    # Profile execution
    print("\n--- Execution Phase (crew.kickoff) ---")
    profiler3 = DetailedProfiler()
    exec_start = time.perf_counter()
    profiler3.start()
    response = crew.kickoff()
    profiler3.stop()
    exec_time = time.perf_counter() - exec_start
    print(f"Execution time: {exec_time*1000:.2f}ms ({exec_time:.2f}s)")
    print(f"Response: {str(response)[:100]}")
    
    print("\nTop 50 functions during execution (by cumulative time):")
    print("-" * 80)
    breakdown = profiler3.get_detailed_breakdown(limit=50)
    print(f"{'Function':<40} {'File':<50} {'Calls':>8} {'CumTime':>10}")
    print("-" * 80)
    for item in breakdown:
        func = item['function'][:38]
        file = item['file'].split('/')[-1][:48] if '/' in item['file'] else item['file'][:48]
        print(f"{func:<40} {file:<50} {item['calls']:>8} {item['cumulative_time']*1000:>9.2f}ms")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY: CrewAI")
    print("=" * 80)
    print(f"Import time:        {import_time*1000:>10.2f}ms")
    print(f"Instantiation time: {inst_time*1000:>10.2f}ms")
    print(f"Execution time:     {exec_time*1000:>10.2f}ms")
    print(f"Total time:         {(import_time+inst_time+exec_time)*1000:>10.2f}ms")
    
    return {
        'import_time': import_time,
        'instantiation_time': inst_time,
        'execution_time': exec_time,
        'total_time': import_time + inst_time + exec_time,
    }


def compare_results(results):
    """Compare results across frameworks."""
    print("\n" + "=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)
    
    print(f"\n{'Framework':<20} {'Import':<12} {'Instantiate':<12} {'Execute':<12} {'Total':<12}")
    print("-" * 68)
    
    # Sort by execution time
    sorted_results = sorted(results.items(), key=lambda x: x[1]['execution_time'])
    fastest_exec = sorted_results[0][1]['execution_time']
    
    for name, times in sorted_results:
        import_ms = times['import_time'] * 1000
        inst_ms = times['instantiation_time'] * 1000
        exec_ms = times['execution_time'] * 1000
        total_ms = times['total_time'] * 1000
        ratio = times['execution_time'] / fastest_exec
        
        print(f"{name:<20} {import_ms:>10.1f}ms {inst_ms:>10.1f}ms {exec_ms:>10.1f}ms {total_ms:>10.1f}ms ({ratio:.2f}x)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PraisonAI Agents - Detailed Profiling Benchmark')
    parser.add_argument('--framework', '-f', type=str, default='all', 
                        choices=['all', 'praisonai', 'agno', 'crewai'],
                        help='Framework to profile (default: all)')
    parser.add_argument('--model', '-m', type=str, default=DEFAULT_MODEL, 
                        help=f'Model to use (default: {DEFAULT_MODEL})')
    parser.add_argument('--prompt', '-p', type=str, default=DEFAULT_PROMPT, 
                        help=f'Prompt to use')
    args = parser.parse_args()
    
    # Check API key
    if not os.environ.get('OPENAI_API_KEY'):
        print("ERROR: Set OPENAI_API_KEY environment variable")
        exit(1)
    
    print("=" * 80)
    print("PraisonAI Agents - Detailed Profiling Benchmark")
    print("=" * 80)
    print(f"\nModel: {args.model}")
    print(f"Prompt: \"{args.prompt}\"")
    print(f"Framework: {args.framework}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    if args.framework in ['all', 'praisonai']:
        try:
            results['PraisonAI'] = profile_praisonai_detailed(args.model, args.prompt)
        except Exception as e:
            print(f"PraisonAI error: {e}")
            import traceback
            traceback.print_exc()
    
    if args.framework in ['all', 'agno']:
        try:
            results['Agno'] = profile_agno_detailed(args.model, args.prompt)
        except Exception as e:
            print(f"Agno error: {e}")
            import traceback
            traceback.print_exc()
    
    if args.framework in ['all', 'crewai']:
        try:
            results['CrewAI'] = profile_crewai_detailed(args.model, args.prompt)
        except Exception as e:
            print(f"CrewAI error: {e}")
            import traceback
            traceback.print_exc()
    
    if len(results) > 1:
        compare_results(results)
    
    print("\n" + "=" * 80)
    print("Profiling complete!")
    print("=" * 80)
