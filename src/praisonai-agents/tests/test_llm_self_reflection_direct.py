#!/usr/bin/env python3
"""Test LLM class directly to verify self-reflection fix"""

from praisonaiagents.llm import LLM
from praisonaiagents.tools import calculator

def test_llm_direct():
    """Test LLM class directly with self-reflection and tools"""
    print("=== Testing LLM Direct with Self-Reflection and Tools ===")
    
    # Create LLM instance
    llm = LLM(model="gpt-4o-mini")
    
    # Test with self-reflection and tools
    try:
        response = llm.get_response(
            prompt="Calculate 15 * 23 and verify your answer",
            system_prompt="You are a helpful math assistant. Use tools when needed.",
            tools=[calculator],
            self_reflect=True,
            min_reflect=1,
            max_reflect=2,
            verbose=True
        )
        
        print(f"\nResponse: {response}")
        
        assert response, "LLM self-reflection with tools failed to produce a response."
        print("\n✅ SUCCESS: LLM self-reflection with tools is working!")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        raise AssertionError(f"Test failed with error: {str(e)}")

if __name__ == "__main__":
    test_llm_direct()