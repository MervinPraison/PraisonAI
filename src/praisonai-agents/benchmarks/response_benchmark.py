"""
PraisonAI Agents - Response Time Benchmark

Measures actual LLM response time with gpt-4o-mini across frameworks.

Usage:
    python benchmarks/response_benchmark.py
"""

import time
import statistics
import os
from typing import List, Literal
from dataclasses import dataclass, field

# Ensure we use gpt-4o-mini
os.environ['OPENAI_MODEL_NAME'] = 'gpt-4o-mini'


@dataclass
class ResponseResult:
    """Response time measurement results"""
    response_times: List[float] = field(default_factory=list)
    
    @property
    def avg_time(self) -> float:
        return statistics.mean(self.response_times) if self.response_times else 0
    
    @property
    def min_time(self) -> float:
        return min(self.response_times) if self.response_times else 0
    
    @property
    def max_time(self) -> float:
        return max(self.response_times) if self.response_times else 0
    
    @property
    def std_dev(self) -> float:
        return statistics.stdev(self.response_times) if len(self.response_times) > 1 else 0


def get_weather(city: Literal["nyc", "sf"]):
    """Use this to get weather information."""
    if city == "nyc":
        return "It might be cloudy in nyc"
    elif city == "sf":
        return "It's always sunny in sf"


def benchmark_praisonai_response(iterations: int = 5) -> ResponseResult:
    """Benchmark PraisonAI agent response time"""
    from praisonaiagents import Agent
    
    result = ResponseResult()
    
    for i in range(iterations):
        print(f"  PraisonAI iteration {i+1}/{iterations}...")
        
        # Create fresh agent each time
        agent = Agent(
            name="Test Agent",
            instructions="Be concise, reply with one sentence.",
            llm="gpt-4o-mini",
            verbose=False
        )
        
        start = time.perf_counter()
        response = agent.start("What is the capital of France?")
        end = time.perf_counter()
        
        result.response_times.append(end - start)
        print(f"    Response time: {end - start:.3f}s")
    
    return result


def benchmark_agno_response(iterations: int = 5) -> ResponseResult:
    """Benchmark Agno agent response time"""
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    
    result = ResponseResult()
    
    for i in range(iterations):
        print(f"  Agno iteration {i+1}/{iterations}...")
        
        # Create fresh agent each time
        agent = Agent(
            model=OpenAIChat(id="gpt-4o-mini"),
            system_message="Be concise, reply with one sentence.",
        )
        
        start = time.perf_counter()
        response = agent.run("What is the capital of France?")
        end = time.perf_counter()
        
        result.response_times.append(end - start)
        print(f"    Response time: {end - start:.3f}s")
    
    return result


def benchmark_praisonai_with_tool(iterations: int = 5) -> ResponseResult:
    """Benchmark PraisonAI agent response time with tool calling"""
    from praisonaiagents import Agent
    
    result = ResponseResult()
    
    for i in range(iterations):
        print(f"  PraisonAI (with tool) iteration {i+1}/{iterations}...")
        
        agent = Agent(
            name="Weather Agent",
            instructions="You are a weather assistant. Use the get_weather tool to answer questions.",
            llm="gpt-4o-mini",
            tools=[get_weather],
            verbose=False
        )
        
        start = time.perf_counter()
        response = agent.start("What's the weather in NYC?")
        end = time.perf_counter()
        
        result.response_times.append(end - start)
        print(f"    Response time: {end - start:.3f}s")
    
    return result


def benchmark_agno_with_tool(iterations: int = 5) -> ResponseResult:
    """Benchmark Agno agent response time with tool calling"""
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    
    result = ResponseResult()
    
    for i in range(iterations):
        print(f"  Agno (with tool) iteration {i+1}/{iterations}...")
        
        agent = Agent(
            model=OpenAIChat(id="gpt-4o-mini"),
            system_message="You are a weather assistant. Use the get_weather tool to answer questions.",
            tools=[get_weather],
        )
        
        start = time.perf_counter()
        response = agent.run("What's the weather in NYC?")
        end = time.perf_counter()
        
        result.response_times.append(end - start)
        print(f"    Response time: {end - start:.3f}s")
    
    return result


if __name__ == "__main__":
    print("="*70)
    print("PraisonAI Agents - Response Time Benchmark")
    print("="*70)
    print("\nModel: gpt-4o-mini")
    print("Measures end-to-end response time including:")
    print("  - Agent instantiation")
    print("  - API call to OpenAI")
    print("  - Response processing")
    
    iterations = 5
    results = {}
    
    # Test 1: Simple response (no tools)
    print("\n" + "="*70)
    print("TEST 1: Simple Response (No Tools)")
    print("="*70)
    
    print("\nBenchmarking PraisonAI...")
    try:
        results['praisonai_simple'] = benchmark_praisonai_response(iterations)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\nBenchmarking Agno...")
    try:
        results['agno_simple'] = benchmark_agno_response(iterations)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: Response with tool calling
    print("\n" + "="*70)
    print("TEST 2: Response with Tool Calling")
    print("="*70)
    
    print("\nBenchmarking PraisonAI with tool...")
    try:
        results['praisonai_tool'] = benchmark_praisonai_with_tool(iterations)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\nBenchmarking Agno with tool...")
    try:
        results['agno_tool'] = benchmark_agno_with_tool(iterations)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY RESULTS")
    print("="*70)
    
    print(f"\n{'Test':<30} {'PraisonAI (avg)':<20} {'Agno (avg)':<20} {'Ratio':<15}")
    print("-" * 85)
    
    if 'praisonai_simple' in results and 'agno_simple' in results:
        p_time = results['praisonai_simple'].avg_time
        a_time = results['agno_simple'].avg_time
        ratio = p_time / a_time if a_time > 0 else float('inf')
        print(f"{'Simple Response':<30} {p_time:<20.3f}s {a_time:<20.3f}s {ratio:.2f}x")
    
    if 'praisonai_tool' in results and 'agno_tool' in results:
        p_time = results['praisonai_tool'].avg_time
        a_time = results['agno_tool'].avg_time
        ratio = p_time / a_time if a_time > 0 else float('inf')
        print(f"{'With Tool Calling':<30} {p_time:<20.3f}s {a_time:<20.3f}s {ratio:.2f}x")
    
    print("\n" + "="*70)
    print("NOTE")
    print("="*70)
    print("\nResponse time is dominated by OpenAI API latency.")
    print("Agent instantiation overhead is negligible in real-world usage.")
