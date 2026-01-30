"""
PraisonAI Output UX Examples

This example demonstrates the various output modes and configurations
available in PraisonAI agents.

Features demonstrated:
- output="verbose": Full output with agent info, task, and response panels
- output="minimal": Clean output with just the result
- Tool call display with consolidated output
- Multi-agent output with clear attribution
"""

import sys
sys.path.insert(0, '/Users/praison/praisonai-package/src/praisonai-agents')
from praisonaiagents import Agent, Task, Agents


def get_weather(city: str) -> str:
    """Get the current weather for a city.
    
    Args:
        city: The name of the city to get weather for
    
    Returns:
        Weather information string
    """
    return f"The weather in {city} is sunny and 72°F"


def example_verbose_true():
    """Example with output='verbose' - shows full output panels."""
    print("\n" + "=" * 60)
    print("EXAMPLE 1: output='verbose' (Full Output)")
    print("=" * 60)
    
    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant. Be concise.",
        output="verbose"  # Shows Agent Info, Task, and Response panels
    )
    result = agent.start("What is the capital of France? Answer in one sentence.")
    print(f"\nReturned value: {result}")


def example_verbose_false():
    """Example with output='minimal' - clean output, just the result."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: output='minimal' (Clean Output)")
    print("=" * 60)
    
    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant. Be concise.",
        output="minimal"  # No panels, just returns the result
    )
    result = agent.start("What is 2+2? Answer in one word.")
    print(f"Result: {result}")


def example_with_tools():
    """Example showing tool call output."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Agent with Tools")
    print("=" * 60)
    
    agent = Agent(
        name="Weather Bot",
        instructions="You help users check the weather. Use the get_weather tool.",
        tools=[get_weather],
        output="verbose"
    )
    result = agent.start("What's the weather in Tokyo?")
    print(f"\nReturned value: {result}")


def example_multi_agent():
    """Example showing multi-agent output with clear attribution."""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Multi-Agent Output")
    print("=" * 60)
    
    researcher = Agent(
        name="Researcher",
        role="Research Analyst",
        instructions="You research topics and provide factual information.",
        output="verbose"
    )
    
    writer = Agent(
        name="Writer",
        role="Content Writer",
        instructions="You write clear summaries based on research.",
        output="verbose"
    )
    
    task1 = Task(
        description="Research what AI is in one sentence",
        expected_output="A brief factual description",
        agent=researcher
    )
    
    task2 = Task(
        description="Write a one-sentence summary about AI",
        expected_output="A clear summary",
        agent=writer
    )
    
    agents = AgentManager(
        agents=[researcher, writer],
        tasks=[task1, task2],
        process="sequential",
        output="verbose"
    )
    
    result = agents.start()
    print(f"\nFinal result: {result}")


if __name__ == "__main__":
    print("=" * 60)
    print("PRAISONAI OUTPUT UX EXAMPLES")
    print("=" * 60)
    
    # Run examples
    example_verbose_true()
    example_verbose_false()
    example_with_tools()
    example_multi_agent()
    
    print("\n" + "=" * 60)
    print("ALL EXAMPLES COMPLETE")
    print("=" * 60)
