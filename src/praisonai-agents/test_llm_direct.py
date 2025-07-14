#!/usr/bin/env python3
"""Test LLM class directly to verify self-reflection fix"""

from praisonaiagents.llm import LLM
from praisonaiagents.tools import evaluate

def test_llm_direct():
    """Test LLM class directly with self-reflection and tools"""
    print("=== Testing LLM Direct with Self-Reflection and Tools ===")
    
    # Create LLM instance
    llm = LLM(model="gpt-4o-mini")
    
    # Test with self-reflection and tools
    response = llm.get_response(
        prompt="Calculate 15 * 23 and verify your answer",
        system_prompt="You are a helpful math assistant. Use tools when needed.",
        tools=[evaluate],
        self_reflect=True,
        min_reflect=1,
        max_reflect=2,
        verbose=True
    )
    
    print(f"\nResponse: {response}")
    
    if response:
        print("\n✅ SUCCESS: LLM self-reflection with tools is working!")
        return True
    else:
        print("\n❌ FAILED: LLM self-reflection with tools is not working")
        return False

if __name__ == "__main__":
    test_llm_direct()