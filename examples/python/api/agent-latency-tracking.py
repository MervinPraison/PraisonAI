"""
Example of using latency tracking with PraisonAI agents.

This shows how to measure latency for different phases:
- Planning: Time spent processing prompts and deciding what to do
- Tool Usage: Time spent executing tools
- LLM Generation: Time spent calling the LLM API
"""

from praisonaiagents import Agent
from praisonaiagents.monitoring import (
    enable_tracking,
    start_request,
    end_request,
    get_latency_summary,
    disable_tracking
)
import time

# Enable latency tracking
enable_tracking()

# Create some example tools
def search_web(query: str) -> str:
    """Simulate web search"""
    time.sleep(0.5)  # Simulate network delay
    return f"Search results for '{query}': Found 10 relevant articles."

def calculate(expression: str) -> str:
    """Evaluate a mathematical expression"""
    time.sleep(0.1)  # Simulate computation
    try:
        result = eval(expression)
        return f"Result: {result}"
    except:
        return "Invalid expression"

# Create an agent with tools
agent = Agent(
    name="ResearchAssistant",
    role="Research Assistant",
    goal="Help users find information and perform calculations",
    backstory="You are a helpful research assistant with access to web search and calculation tools.",
    tools=[search_web, calculate],
    llm="gpt-4o-mini"  # or any other model
)

# Example 1: Simple query without tools
print("Example 1: Simple query")
start_request("simple_query")
response = agent.chat("What is artificial intelligence?")
metrics = end_request()
print(f"Response: {response[:100]}...")
print(f"Total time: {metrics['total_time']:.3f}s")
print(f"Phases: {list(metrics['phases'].keys())}\n")

# Example 2: Query with tool usage
print("Example 2: Query with tool usage")
start_request("tool_query")
response = agent.chat("Search for information about quantum computing")
metrics = end_request()
print(f"Response: {response[:100]}...")
print(f"Total time: {metrics['total_time']:.3f}s")
for phase, data in metrics['phases'].items():
    print(f"  {phase}: {data['total']:.3f}s")
print()

# Example 3: Multiple tool calls
print("Example 3: Multiple tool calls")
start_request("multi_tool_query")
response = agent.chat("Search for Python tutorials and calculate 42 * 17")
metrics = end_request()
print(f"Response: {response[:100]}...")
print(f"Total time: {metrics['total_time']:.3f}s")
for phase, data in metrics['phases'].items():
    print(f"  {phase}: {data['total']:.3f}s ({data['count']} calls)")
print()

# Get overall summary
print("\n=== Overall Latency Summary ===")
summary = get_latency_summary()
for phase, stats in summary['phases'].items():
    if stats['total_requests'] > 0:
        print(f"\n{phase.upper()}:")
        print(f"  Total requests: {stats['total_requests']}")
        print(f"  Average time: {stats['average_time']:.3f}s")
        print(f"  Min time: {stats['min_time']:.3f}s")
        print(f"  Max time: {stats['max_time']:.3f}s")
        print(f"  Total time: {stats['total_time']:.3f}s")

# Disable tracking when done
disable_tracking()