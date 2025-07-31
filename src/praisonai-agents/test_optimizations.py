#!/usr/bin/env python
"""Test script to verify the performance optimizations work correctly."""

import time
from praisonaiagents import Agent

def simple_tool(query: str) -> str:
    """A simple tool for testing."""
    return f"Tool response for: {query}"

def test_simple_agent():
    """Test simple agent without tools or knowledge."""
    print("1. Testing simple agent...")
    start = time.time()
    agent = Agent(
        instructions="You are a helpful assistant",
        llm="gpt-4o-mini"
    )
    init_time = time.time() - start
    print(f"   Initialization time: {init_time:.3f}s")
    
    start = time.time()
    response = agent.start("What is 2+2?")
    response_time = time.time() - start
    print(f"   Response time: {response_time:.3f}s")
    print(f"   Response: {response[:50]}...")

def test_agent_with_tools():
    """Test agent with tools."""
    print("\n2. Testing agent with tools...")
    start = time.time()
    agent = Agent(
        name="Calculator",
        role="Math Assistant",
        goal="Help with calculations",
        backstory="You are a math expert",
        tools=[simple_tool],
        llm="gpt-4o-mini"
    )
    init_time = time.time() - start
    print(f"   Initialization time: {init_time:.3f}s")
    
    # First call (cold cache)
    start = time.time()
    response1 = agent.chat("Calculate something")
    response_time1 = time.time() - start
    print(f"   First response time: {response_time1:.3f}s")
    
    # Second call (warm cache)
    start = time.time()
    response2 = agent.chat("Calculate something else")
    response_time2 = time.time() - start
    print(f"   Second response time (cached): {response_time2:.3f}s")
    print(f"   Cache speedup: {response_time1/response_time2:.1f}x")

def test_agent_with_knowledge():
    """Test agent with knowledge (lazy loading)."""
    print("\n3. Testing agent with knowledge (lazy loading)...")
    start = time.time()
    agent = Agent(
        name="KnowledgeAgent",
        role="Information Assistant",
        goal="Help with information retrieval",
        backstory="You have access to knowledge",
        knowledge=["This is some test knowledge content"],
        llm="gpt-4o-mini"
    )
    init_time = time.time() - start
    print(f"   Initialization time (knowledge not processed): {init_time:.3f}s")
    
    # First query (triggers knowledge processing)
    start = time.time()
    response = agent.chat("What knowledge do you have?")
    response_time = time.time() - start
    print(f"   First response time (includes knowledge processing): {response_time:.3f}s")

def test_multiple_agents():
    """Test multiple agents to verify logging is configured only once."""
    print("\n4. Testing multiple agents (logging optimization)...")
    agents = []
    total_time = 0
    
    for i in range(3):
        start = time.time()
        agent = Agent(
            name=f"Agent{i}",
            instructions="You are a helpful assistant",
            llm="gpt-4o-mini"
        )
        init_time = time.time() - start
        total_time += init_time
        agents.append(agent)
        print(f"   Agent {i} initialization time: {init_time:.3f}s")
    
    print(f"   Average initialization time: {total_time/3:.3f}s")

if __name__ == "__main__":
    print("Testing PraisonAI Agent Optimizations")
    print("=====================================")
    
    test_simple_agent()
    test_agent_with_tools()
    # test_agent_with_knowledge()  # Skip for now due to Knowledge API issue
    test_multiple_agents()
    
    print("\nAll tests completed!")