#!/usr/bin/env python3
"""Test self-reflection functionality in both Agent and LLM classes"""

from praisonaiagents import Agent
from praisonaiagents.llm import LLM

def test_agent_self_reflection():
    """Test self-reflection in Agent class"""
    print("=== Testing Agent Self-Reflection ===")
    agent = Agent(
        name="ReflectiveAgent",
        instructions="You are a helpful assistant.",
        llm="gpt-4o-mini",
        self_reflect=True,
        min_reflect=1,
        max_reflect=3
    )
    
    response = agent.start("What is 2+2? Be brief.")
    print(f"Agent Response: {response}")
    print()

def test_llm_self_reflection():
    """Test self-reflection in LLM class directly"""
    print("=== Testing LLM Self-Reflection ===")
    llm = LLM(model="gpt-4o-mini")
    
    response = llm.get_response(
        prompt="What is 2+2? Be brief.",
        system_prompt="You are a helpful assistant.",
        self_reflect=True,
        min_reflect=1,
        max_reflect=3,
        verbose=True
    )
    print(f"LLM Response: {response}")
    print()

def test_llm_no_reflection():
    """Test LLM without self-reflection for comparison"""
    print("=== Testing LLM Without Self-Reflection ===")
    llm = LLM(model="gpt-4o-mini")
    
    response = llm.get_response(
        prompt="What is 2+2? Be brief.",
        system_prompt="You are a helpful assistant.",
        self_reflect=False,
        verbose=True
    )
    print(f"LLM Response: {response}")
    print()

if __name__ == "__main__":
    # Test without reflection first
    test_llm_no_reflection()
    
    # Test with reflection
    test_llm_self_reflection()
    
    # Test agent reflection
    test_agent_self_reflection()