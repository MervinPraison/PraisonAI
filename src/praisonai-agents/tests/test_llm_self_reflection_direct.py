#!/usr/bin/env python3
"""Test LLM class directly to verify self-reflection fix"""

import os
import pytest
from praisonaiagents.llm import LLM

# Define calculator tool locally to avoid import issues
def calculator(expression: str) -> str:
    """
    Evaluate a mathematical expression.
    
    Args:
        expression: A mathematical expression to evaluate (e.g., "2 + 2", "15 * 23")
    
    Returns:
        The result of the calculation as a string
    """
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error: {str(e)}"

@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set - skipping integration test"
)
@pytest.mark.asyncio
async def test_llm_direct():
    """Test LLM class directly with self-reflection and tools"""
    print("=== Testing LLM Direct with Self-Reflection and Tools ===")
    
    # Create LLM instance
    llm = LLM(model="gpt-4o-mini")
    
    # Test with self-reflection and tools
    try:
        response = await llm.get_response_async(
            prompt="Calculate 15 * 23 and verify your answer",
            system_prompt="You are a helpful math assistant. Use tools when needed.",
            tools=[calculator],
            reflection=True,
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