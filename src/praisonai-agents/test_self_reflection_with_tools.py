#!/usr/bin/env python3
"""Test script to verify self-reflection works with tools after the fix"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import duckduckgo_search

def test_self_reflection_with_tools():
    """Test self-reflection with tools - should work after the fix"""
    print("=== Testing Self-Reflection WITH Tools ===")
    
    # Create an agent with self-reflection and tools
    agent = Agent(
        role="Senior Research Analyst",
        goal="Analyze and provide insights on given topics",
        backstory="You are an expert analyst with strong critical thinking skills",
        self_reflect=True,
        llm="gemini/gemini-2.5-flash-lite-preview-06-17",
        verbose=True,
        tools=[duckduckgo_search]
    )

    # Create a task
    task = Task(
        description="Search for recent developments in AI and provide a brief analysis",
        expected_output="A detailed analysis report",
        agent=agent
    )

    # Create and start the agents
    agents = PraisonAIAgents(
        agents=[agent],
        tasks=[task],
        process="sequential"
    )

    # Start execution
    result = agents.start()
    print(f"Result with tools: {result}")
    return result

def test_self_reflection_without_tools():
    """Test self-reflection without tools - should work (baseline)"""
    print("\n=== Testing Self-Reflection WITHOUT Tools ===")
    
    # Create an agent with self-reflection but no tools
    agent = Agent(
        role="Senior Research Analyst",
        goal="Analyze and provide insights on given topics",
        backstory="You are an expert analyst with strong critical thinking skills",
        self_reflect=True,
        llm="gemini/gemini-2.5-flash-lite-preview-06-17",
        verbose=True
    )

    # Create a task
    task = Task(
        description="Analyze recent developments in AI",
        expected_output="A detailed analysis report",
        agent=agent
    )

    # Create and start the agents
    agents = PraisonAIAgents(
        agents=[agent],
        tasks=[task],
        process="sequential"
    )

    # Start execution
    result = agents.start()
    print(f"Result without tools: {result}")
    return result

if __name__ == "__main__":
    print("Testing self-reflection fix...")
    
    # Test without tools (should work)
    result_without_tools = test_self_reflection_without_tools()
    
    # Test with tools (should work after fix)
    result_with_tools = test_self_reflection_with_tools()
    
    print("\n=== Test Summary ===")
    print(f"Without tools: {'SUCCESS' if result_without_tools else 'FAILED'}")
    print(f"With tools: {'SUCCESS' if result_with_tools else 'FAILED'}")
    
    if result_with_tools:
        print("\n✅ Fix verified: Self-reflection now works with tools!")
    else:
        print("\n❌ Fix failed: Self-reflection still not working with tools")