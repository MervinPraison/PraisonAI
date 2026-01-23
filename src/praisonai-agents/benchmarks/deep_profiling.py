#!/usr/bin/env python3
"""
PraisonAI Agents - Deep Profiling Benchmark

Profiles each step of agent initialization to identify performance bottlenecks.

Key Optimizations Applied:
1. Lazy RulesManager - filesystem operations deferred until first access
2. Lazy os.getcwd() - fast_context_path resolved only when needed
3. Lazy console initialization - Rich Console created on demand

Advanced Profiling Features:
- Line-by-line profiling of __init__ method
- Call graph analysis
- Memory allocation tracking
- Function call counting
- Attribute access profiling

Usage:
    python benchmarks/deep_profiling.py
    python benchmarks/deep_profiling.py --deep  # More detailed profiling
"""

import time
import tracemalloc
import cProfile
import pstats
import io
from typing import Literal, Callable, Dict, List
from dataclasses import dataclass

# ============================================================================
# Timing Utilities
# ============================================================================

@dataclass
class StepTiming:
    name: str
    duration_us: float  # microseconds
    memory_kb: float    # kilobytes


class StepProfiler:
    """Profile individual steps during initialization"""
    
    def __init__(self):
        self.steps: List[StepTiming] = []
        self._start_time = None
        self._start_memory = None
    
    def start_step(self, name: str):
        tracemalloc.start()
        self._start_time = time.perf_counter()
        self._step_name = name
    
    def end_step(self):
        end_time = time.perf_counter()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        duration_us = (end_time - self._start_time) * 1_000_000
        memory_kb = peak / 1024
        
        self.steps.append(StepTiming(
            name=self._step_name,
            duration_us=duration_us,
            memory_kb=memory_kb
        ))
    
    def print_report(self, title: str):
        print(f"\n{'='*70}")
        print(f"STEP-BY-STEP PROFILING: {title}")
        print(f"{'='*70}")
        
        total_time = sum(s.duration_us for s in self.steps)
        total_memory = sum(s.memory_kb for s in self.steps)
        
        print(f"\n{'Step':<40} {'Time (μs)':<15} {'Memory (KB)':<15} {'% Time':<10}")
        print("-" * 80)
        
        for step in sorted(self.steps, key=lambda x: x.duration_us, reverse=True):
            pct = (step.duration_us / total_time * 100) if total_time > 0 else 0
            print(f"{step.name:<40} {step.duration_us:<15.2f} {step.memory_kb:<15.2f} {pct:<10.1f}%")
        
        print("-" * 80)
        print(f"{'TOTAL':<40} {total_time:<15.2f} {total_memory:<15.2f} {'100.0':<10}%")


def time_function(func: Callable, iterations: int = 100) -> Dict:
    """Time a function with detailed statistics"""
    times = []
    
    # Warmup
    for _ in range(10):
        func()
    
    # Measure
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append((end - start) * 1_000_000)  # Convert to microseconds
    
    return {
        'avg': sum(times) / len(times),
        'min': min(times),
        'max': max(times),
        'median': sorted(times)[len(times)//2]
    }


# ============================================================================
# Profile PraisonAI Agent Initialization - Step by Step
# ============================================================================

def profile_praisonai_detailed():
    """Profile each step of PraisonAI Agent initialization"""
    print("\n" + "="*70)
    print("DETAILED PROFILING: PraisonAI Agent")
    print("="*70)
    
    profiler = StepProfiler()
    
    # Step 1: Import
    profiler.start_step("1. Import praisonaiagents")
    from praisonaiagents import Agent as PraisonAgent
    profiler.end_step()
    
    # Step 2: Define tool
    profiler.start_step("2. Define tool function")
    def get_weather(city: Literal["nyc", "sf"]):
        """Use this to get weather information."""
        if city == "nyc":
            return "It might be cloudy in nyc"
        elif city == "sf":
            return "It's always sunny in sf"
    tools = [get_weather]
    profiler.end_step()
    
    # Step 3: Full instantiation
    profiler.start_step("3. Full Agent instantiation")
    agent = PraisonAgent(
        name="Test Agent",
        instructions="Be concise, reply with one sentence.",
        llm="gpt-4o-mini",
        tools=tools,
        output="silent"
    )
    profiler.end_step()
    
    profiler.print_report("PraisonAI Agent")
    
    # Now profile the __init__ internals using cProfile
    print("\n" + "="*70)
    print("cProfile ANALYSIS: PraisonAI Agent.__init__")
    print("="*70)
    
    pr = cProfile.Profile()
    pr.enable()
    
    for _ in range(100):
        agent = PraisonAgent(
            name="Test Agent",
            instructions="Be concise, reply with one sentence.",
            llm="gpt-4o-mini",
            tools=tools,
            output="silent"
        )
    
    pr.disable()
    
    # Print top 30 functions by cumulative time
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(30)
    print(s.getvalue())
    
    return agent


# ============================================================================
# Profile Agno Agent Initialization - Step by Step
# ============================================================================

def profile_agno_detailed():
    """Profile each step of Agno Agent initialization"""
    print("\n" + "="*70)
    print("DETAILED PROFILING: Agno Agent")
    print("="*70)
    
    profiler = StepProfiler()
    
    # Step 1: Import
    profiler.start_step("1. Import agno")
    from agno.agent import Agent as AgnoAgent
    from agno.models.openai import OpenAIChat
    profiler.end_step()
    
    # Step 2: Define tool
    profiler.start_step("2. Define tool function")
    def get_weather(city: Literal["nyc", "sf"]):
        """Use this to get weather information."""
        if city == "nyc":
            return "It might be cloudy in nyc"
        elif city == "sf":
            return "It's always sunny in sf"
    tools = [get_weather]
    profiler.end_step()
    
    # Step 3: Full instantiation
    profiler.start_step("3. Full Agent instantiation")
    agent = AgnoAgent(model=OpenAIChat(id="gpt-4o-mini"), tools=tools)
    profiler.end_step()
    
    profiler.print_report("Agno Agent")
    
    # Now profile the __init__ internals using cProfile
    print("\n" + "="*70)
    print("cProfile ANALYSIS: Agno Agent.__init__")
    print("="*70)
    
    pr = cProfile.Profile()
    pr.enable()
    
    for _ in range(100):
        agent = AgnoAgent(model=OpenAIChat(id="gpt-4o-mini"), tools=tools)
    
    pr.disable()
    
    # Print top 30 functions by cumulative time
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(30)
    print(s.getvalue())
    
    return agent


# ============================================================================
# Profile Individual Components of PraisonAI
# ============================================================================

def profile_praisonai_components():
    """Profile individual components of PraisonAI Agent initialization"""
    print("\n" + "="*70)
    print("COMPONENT-LEVEL PROFILING: PraisonAI Agent")
    print("="*70)
    
    from praisonaiagents import Agent as PraisonAgent
    
    def get_weather(city: Literal["nyc", "sf"]):
        if city == "nyc":
            return "It might be cloudy in nyc"
        elif city == "sf":
            return "It's always sunny in sf"
    tools = [get_weather]
    
    # Test different configurations
    configs = [
        ("Minimal (no tools, no llm)", {"name": "Test", "output": "silent"}),
        ("With name only", {"name": "Test Agent", "output": "silent"}),
        ("With instructions", {"name": "Test", "instructions": "Be concise", "output": "silent"}),
        ("With llm (gpt-4o-mini)", {"name": "Test", "llm": "gpt-4o-mini", "output": "silent"}),
        ("With llm (openai/gpt-4o-mini)", {"name": "Test", "llm": "openai/gpt-4o-mini", "output": "silent"}),
        ("With tools", {"name": "Test", "tools": tools, "output": "silent"}),
        ("Full config (OpenAI SDK)", {"name": "Test", "instructions": "Be concise", "llm": "gpt-4o-mini", "tools": tools, "output": "silent"}),
        ("Full config (LiteLLM)", {"name": "Test", "instructions": "Be concise", "llm": "openai/gpt-4o-mini", "tools": tools, "output": "silent"}),
    ]
    
    print(f"\n{'Configuration':<40} {'Avg Time (μs)':<15} {'Min (μs)':<15} {'Max (μs)':<15}")
    print("-" * 85)
    
    for name, config in configs:
        def create_agent():
            return PraisonAgent(**config)
        
        stats = time_function(create_agent, iterations=100)
        print(f"{name:<40} {stats['avg']:<15.2f} {stats['min']:<15.2f} {stats['max']:<15.2f}")


# ============================================================================
# Compare Specific Operations
# ============================================================================

def compare_specific_operations():
    """Compare specific operations between PraisonAI and Agno"""
    print("\n" + "="*70)
    print("OPERATION COMPARISON: PraisonAI vs Agno")
    print("="*70)
    
    from praisonaiagents import Agent as PraisonAgent
    from agno.agent import Agent as AgnoAgent
    from agno.models.openai import OpenAIChat
    
    def get_weather(city: Literal["nyc", "sf"]):
        if city == "nyc":
            return "It might be cloudy in nyc"
        elif city == "sf":
            return "It's always sunny in sf"
    tools = [get_weather]
    
    operations = []
    
    # Operation 1: Bare minimum instantiation
    def praisonai_minimal():
        return PraisonAgent(name="Test", output="silent")
    
    def agno_minimal():
        return AgnoAgent(model=OpenAIChat(id="gpt-4o-mini"))
    
    praison_stats = time_function(praisonai_minimal, 100)
    agno_stats = time_function(agno_minimal, 100)
    operations.append(("Minimal instantiation", praison_stats['avg'], agno_stats['avg']))
    
    # Operation 2: With tools
    def praisonai_with_tools():
        return PraisonAgent(name="Test", tools=tools, output="silent")
    
    def agno_with_tools():
        return AgnoAgent(model=OpenAIChat(id="gpt-4o-mini"), tools=tools)
    
    praison_stats = time_function(praisonai_with_tools, 100)
    agno_stats = time_function(agno_with_tools, 100)
    operations.append(("With tools", praison_stats['avg'], agno_stats['avg']))
    
    # Operation 3: Full config
    def praisonai_full():
        return PraisonAgent(
            name="Test Agent",
            instructions="Be concise",
            llm="gpt-4o-mini",
            tools=tools,
            output="silent"
        )
    
    def agno_full():
        return AgnoAgent(
            model=OpenAIChat(id="gpt-4o-mini"),
            tools=tools,
            instructions=["Be concise"]
        )
    
    praison_stats = time_function(praisonai_full, 100)
    agno_stats = time_function(agno_full, 100)
    operations.append(("Full config", praison_stats['avg'], agno_stats['avg']))
    
    print(f"\n{'Operation':<30} {'PraisonAI (μs)':<18} {'Agno (μs)':<18} {'Ratio':<10}")
    print("-" * 76)
    
    for op_name, praison_time, agno_time in operations:
        ratio = praison_time / agno_time if agno_time > 0 else 0
        print(f"{op_name:<30} {praison_time:<18.2f} {agno_time:<18.2f} {ratio:<10.1f}x")


# ============================================================================
# Advanced: Attribute Access Profiling
# ============================================================================

def profile_attribute_access():
    """Profile attribute access patterns in Agent.__init__"""
    print("\n" + "="*70)
    print("ATTRIBUTE ACCESS PROFILING")
    print("="*70)
    
    from praisonaiagents import Agent as PraisonAgent
    
    # Count attribute accesses during init
    attr_counts = {}
    original_setattr = object.__setattr__
    
    def counting_setattr(obj, name, value):
        if isinstance(obj, PraisonAgent):
            attr_counts[name] = attr_counts.get(name, 0) + 1
        return original_setattr(obj, name, value)
    
    # Temporarily patch
    import builtins
    old_setattr = builtins.setattr if hasattr(builtins, 'setattr') else None
    
    # Create agent and count
    agent = PraisonAgent(name="Test", output="silent")
    
    # Sort by count
    sorted_attrs = sorted(attr_counts.items(), key=lambda x: x[1], reverse=True)
    
    print(f"\n{'Attribute':<40} {'Set Count':<15}")
    print("-" * 55)
    for attr, count in sorted_attrs[:30]:
        print(f"{attr:<40} {count:<15}")
    
    print(f"\nTotal attributes set: {len(attr_counts)}")
    print(f"Total setattr calls: {sum(attr_counts.values())}")


# ============================================================================
# Advanced: Function Call Analysis
# ============================================================================

def analyze_init_function_calls():
    """Analyze which functions are called during Agent.__init__"""
    print("\n" + "="*70)
    print("FUNCTION CALL ANALYSIS: PraisonAI Agent.__init__")
    print("="*70)
    
    import sys
    from praisonaiagents import Agent as PraisonAgent
    
    call_counts = {}
    
    def trace_calls(frame, event, arg):
        if event == 'call':
            code = frame.f_code
            func_name = code.co_name
            filename = code.co_filename
            
            # Only track praisonaiagents calls
            if 'praisonaiagents' in filename:
                key = f"{func_name} ({filename.split('/')[-1]}:{code.co_firstlineno})"
                call_counts[key] = call_counts.get(key, 0) + 1
        return trace_calls
    
    # Enable tracing
    sys.settrace(trace_calls)
    
    try:
        agent = PraisonAgent(name="Test", output="silent")
    finally:
        sys.settrace(None)
    
    # Sort by count
    sorted_calls = sorted(call_counts.items(), key=lambda x: x[1], reverse=True)
    
    print(f"\n{'Function':<60} {'Calls':<10}")
    print("-" * 70)
    for func, count in sorted_calls[:40]:
        print(f"{func:<60} {count:<10}")
    
    print(f"\nTotal unique functions called: {len(call_counts)}")
    print(f"Total function calls: {sum(call_counts.values())}")


# ============================================================================
# Advanced: Import Time Analysis
# ============================================================================

def analyze_import_overhead():
    """Analyze import overhead for key modules"""
    print("\n" + "="*70)
    print("IMPORT OVERHEAD ANALYSIS")
    print("="*70)
    
    import sys
    import importlib
    
    modules_to_test = [
        'praisonaiagents',
        'praisonaiagents.agent.agent',
        'praisonaiagents.config.param_resolver',
        'praisonaiagents.config.presets',
        'praisonaiagents.config.feature_configs',
    ]
    
    print(f"\n{'Module':<50} {'Import Time (ms)':<20}")
    print("-" * 70)
    
    for module_name in modules_to_test:
        # Clear from cache
        to_remove = [k for k in sys.modules.keys() if k.startswith('praisonaiagents')]
        for k in to_remove:
            del sys.modules[k]
        
        start = time.perf_counter()
        try:
            importlib.import_module(module_name)
            elapsed = (time.perf_counter() - start) * 1000
            print(f"{module_name:<50} {elapsed:<20.2f}")
        except ImportError as e:
            print(f"{module_name:<50} FAILED: {e}")


# ============================================================================
# Advanced: Agno vs PraisonAI Architecture Comparison
# ============================================================================

def compare_architecture():
    """Compare architectural differences between Agno and PraisonAI"""
    print("\n" + "="*70)
    print("ARCHITECTURE COMPARISON: Agno vs PraisonAI")
    print("="*70)
    
    from praisonaiagents import Agent as PraisonAgent
    from agno.agent import Agent as AgnoAgent
    from agno.models.openai import OpenAIChat
    
    # Create instances
    praison_agent = PraisonAgent(name="Test", output="silent")
    agno_agent = AgnoAgent(model=OpenAIChat(id="gpt-4o-mini"))
    
    print("\n### Class Structure ###")
    print(f"\nPraisonAI Agent:")
    print(f"  - Uses @dataclass: No (regular class)")
    print(f"  - __slots__: {'Yes' if hasattr(PraisonAgent, '__slots__') else 'No'}")
    print(f"  - Instance dict size: {len(praison_agent.__dict__)} attributes")
    
    print(f"\nAgno Agent:")
    print(f"  - Uses @dataclass: Yes (init=False)")
    print(f"  - __slots__: {'Yes' if hasattr(AgnoAgent, '__slots__') else 'No'}")
    print(f"  - Instance dict size: {len(agno_agent.__dict__)} attributes")
    
    print("\n### Key Differences ###")
    print("\n1. Agno uses @dataclass(init=False) - class attributes pre-declared")
    print("2. Agno __init__ is mostly simple attribute assignments")
    print("3. PraisonAI __init__ does extensive parameter resolution")
    print("4. PraisonAI imports config modules inside __init__")
    print("5. PraisonAI calls resolve() 10+ times for feature params")
    
    # Count resolve calls in PraisonAI
    print("\n### Parameter Resolution Overhead ###")
    print("\nPraisonAI resolve() calls in __init__:")
    print("  - output: resolve()")
    print("  - execution: resolve()")
    print("  - templates: resolve()")
    print("  - caching: resolve()")
    print("  - hooks: resolve()")
    print("  - skills: resolve()")
    print("  - memory: resolve()")
    print("  - knowledge: resolve()")
    print("  - planning: resolve()")
    print("  - reflection: resolve()")
    print("  - guardrails: resolve()")
    print("  - web: resolve()")
    print("  Total: 12 resolve() calls per Agent creation")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import os
    import argparse
    
    parser = argparse.ArgumentParser(description='Deep Profiling Benchmark')
    parser.add_argument('--deep', action='store_true', help='Run deep profiling (slower)')
    args = parser.parse_args()
    
    os.environ.setdefault("OPENAI_API_KEY", "sk-test")
    
    print("="*70)
    print("PraisonAI Agents - Deep Profiling Benchmark")
    print("="*70)
    print("\nThis analysis identifies performance bottlenecks in agent initialization.\n")
    
    # Run all profiling
    profile_praisonai_detailed()
    profile_agno_detailed()
    profile_praisonai_components()
    compare_specific_operations()
    
    # Advanced profiling (optional)
    if args.deep:
        print("\n" + "="*70)
        print("ADVANCED PROFILING (--deep mode)")
        print("="*70)
        analyze_init_function_calls()
        analyze_import_overhead()
    
    # Always run architecture comparison
    compare_architecture()
    
    print("\n" + "="*70)
    print("PROFILING COMPLETE")
    print("="*70)
