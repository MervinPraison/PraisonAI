#!/usr/bin/env python3
"""Simple test to verify the self-reflection fix works"""

from praisonaiagents import Agent
from praisonaiagents.tools import calculator

def test_self_reflection_fix():
    """Test that self-reflection works with tools after the fix"""
    print("=== Testing Self-Reflection Fix ===")
    
    # Create an agent with self-reflection and a simple tool
    agent = Agent(
        role="Math Assistant",
        goal="Solve math problems accurately",
        backstory="You are a helpful math assistant",
        self_reflect=True,
        llm="gpt-4o-mini",  # Use a more widely available model
        verbose=True,
        tools=[calculator],
        min_reflect=1,
        max_reflect=2
    )

    # Test with a simple calculation that might trigger self-reflection
    try:
        response = agent.start("What is 25 * 17? Show your work and double-check the answer.")
        print(f"\nResponse: {response}")
        
        assert response, "Self-reflection with tools failed to produce a response."
        print("\n✅ SUCCESS: Self-reflection with tools is working!")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        raise AssertionError(f"Test failed with error: {str(e)}")

if __name__ == "__main__":
    test_self_reflection_fix()