#!/usr/bin/env python
"""Benchmark to compare before and after optimizations."""

import time
import sys
from praisonaiagents import Agent

# Simple tool for testing
def calculator(operation: str) -> str:
    """Perform a calculation."""
    return f"Result of {operation}"

def benchmark_agent_creation(num_agents=10):
    """Benchmark agent creation time."""
    print(f"\nBenchmarking creation of {num_agents} agents...")
    
    times = []
    for i in range(num_agents):
        start = time.time()
        agent = Agent(
            name=f"Agent{i}",
            role="Assistant",
            goal="Help users",
            backstory="I am a helpful assistant",
            tools=[calculator] if i % 2 == 0 else None,  # Half with tools
            llm="gpt-4o-mini"
        )
        creation_time = time.time() - start
        times.append(creation_time)
        
        # Test system prompt caching
        start = time.time()
        _ = agent._build_system_prompt()
        prompt_time1 = time.time() - start
        
        start = time.time()
        _ = agent._build_system_prompt()  # Should be cached
        prompt_time2 = time.time() - start
        
        if i == 0:
            print(f"  Agent 0:")
            print(f"    Creation time: {creation_time:.4f}s")
            print(f"    First system prompt build: {prompt_time1:.4f}s")
            print(f"    Second system prompt build (cached): {prompt_time2:.4f}s")
            print(f"    Cache speedup: {prompt_time1/prompt_time2:.1f}x" if prompt_time2 > 0 else "    Cache speedup: ∞")
    
    avg_time = sum(times) / len(times)
    print(f"\n  Average agent creation time: {avg_time:.4f}s")
    print(f"  Total time for {num_agents} agents: {sum(times):.2f}s")

def benchmark_tool_formatting():
    """Benchmark tool formatting with caching."""
    print("\nBenchmarking tool formatting...")
    
    tools = [calculator, calculator, calculator]  # Multiple tools
    agent = Agent(
        name="ToolAgent",
        role="Tool User",
        goal="Use tools",
        backstory="I use tools",
        tools=tools,
        llm="gpt-4o-mini"
    )
    
    # First format (cold cache)
    start = time.time()
    formatted1 = agent._format_tools_for_completion()
    time1 = time.time() - start
    
    # Second format (warm cache)
    start = time.time()
    formatted2 = agent._format_tools_for_completion()
    time2 = time.time() - start
    
    print(f"  First tool formatting: {time1:.4f}s")
    print(f"  Second tool formatting (cached): {time2:.4f}s")
    print(f"  Cache speedup: {time1/time2:.1f}x" if time2 > 0 else "  Cache speedup: ∞")

def benchmark_console_usage():
    """Benchmark console lazy loading."""
    print("\nBenchmarking console lazy loading...")
    
    # Agent without verbose (console not needed)
    start = time.time()
    agent1 = Agent(
        instructions="Test agent",
        llm="gpt-4o-mini",
        verbose=False
    )
    time_no_console = time.time() - start
    
    # Check if console was created
    console_created = hasattr(agent1, '_console') and agent1._console is not None
    
    print(f"  Agent creation (verbose=False): {time_no_console:.4f}s")
    print(f"  Console created: {console_created}")
    
    # Agent with verbose (console needed)
    start = time.time()
    agent2 = Agent(
        instructions="Test agent",
        llm="gpt-4o-mini",
        verbose=True
    )
    time_with_console = time.time() - start
    
    # Force console access
    start = time.time()
    _ = agent2.console
    console_access_time = time.time() - start
    
    print(f"  Agent creation (verbose=True): {time_with_console:.4f}s")
    print(f"  First console access: {console_access_time:.4f}s")

if __name__ == "__main__":
    print("PraisonAI Agent Performance Benchmark")
    print("=====================================")
    print("This benchmark demonstrates the performance optimizations:")
    print("- Lazy console loading")
    print("- System prompt caching")
    print("- Tool formatting caching")
    print("- One-time logging configuration")
    
    benchmark_agent_creation()
    benchmark_tool_formatting()
    benchmark_console_usage()
    
    print("\nBenchmark completed!")