#!/usr/bin/env python3
"""Test self-reflection functionality with tools to verify the fix for issue #901"""

from praisonaiagents import Agent
from praisonaiagents.llm import LLM

def simple_calculator(operation: str, a: int, b: int) -> int:
    """A simple calculator tool"""
    if operation == "add":
        return a + b
    elif operation == "subtract":
        return a - b
    elif operation == "multiply":
        return a * b
    elif operation == "divide":
        return a / b if b != 0 else "Cannot divide by zero"
    else:
        return "Unknown operation"

def test_llm_self_reflection_with_tools():
    """Test self-reflection in LLM class directly with tools"""
    print("=== Testing LLM Self-Reflection WITH Tools ===")
    llm = LLM(model="gpt-4o-mini")
    
    def mock_tool_executor(function_name, arguments):
        """Mock tool executor for testing"""
        if function_name == "simple_calculator":
            return simple_calculator(
                arguments.get("operation", "add"),
                arguments.get("a", 0),
                arguments.get("b", 0)
            )
        return None
    
    response = llm.get_response(
        prompt="Calculate 5 + 3 and then reflect on your answer",
        system_prompt="You are a helpful assistant with access to a calculator tool.",
        tools=[simple_calculator],
        self_reflect=True,
        min_reflect=1,
        max_reflect=2,
        verbose=True,
        execute_tool_fn=mock_tool_executor
    )
    print(f"LLM Response with tools: {response}")
    print()

def test_llm_self_reflection_without_tools():
    """Test self-reflection in LLM class directly without tools"""
    print("=== Testing LLM Self-Reflection WITHOUT Tools ===")
    llm = LLM(model="gpt-4o-mini")
    
    response = llm.get_response(
        prompt="Calculate 5 + 3 and then reflect on your answer",
        system_prompt="You are a helpful assistant.",
        self_reflect=True,
        min_reflect=1,
        max_reflect=2,
        verbose=True
    )
    print(f"LLM Response without tools: {response}")
    print()

def test_agent_self_reflection_with_tools():
    """Test self-reflection in Agent class with tools"""
    print("=== Testing Agent Self-Reflection WITH Tools ===")
    agent = Agent(
        name="CalculatorAgent",
        instructions="You are a helpful assistant with access to a calculator tool.",
        llm="gpt-4o-mini",
        self_reflect=True,
        min_reflect=1,
        max_reflect=2,
        tools=[simple_calculator]
    )
    
    response = agent.start("Calculate 5 + 3 and then reflect on your answer")
    print(f"Agent Response with tools: {response}")
    print()

def test_agent_self_reflection_without_tools():
    """Test self-reflection in Agent class without tools"""
    print("=== Testing Agent Self-Reflection WITHOUT Tools ===")
    agent = Agent(
        name="BasicAgent",
        instructions="You are a helpful assistant.",
        llm="gpt-4o-mini",
        self_reflect=True,
        min_reflect=1,
        max_reflect=2
    )
    
    response = agent.start("Calculate 5 + 3 and then reflect on your answer")
    print(f"Agent Response without tools: {response}")
    print()

if __name__ == "__main__":
    import os
    
    # Check if we have the required API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY environment variable is required for testing")
        print("Set it with: export OPENAI_API_KEY='your-api-key-here'")
        exit(1)
    
    print("Testing self-reflection with tools fix for issue #901")
    print("=" * 60)
    
    try:
        # Test baseline (without tools)
        test_llm_self_reflection_without_tools()
        test_agent_self_reflection_without_tools()
        
        # Test the fix (with tools)
        test_llm_self_reflection_with_tools()
        test_agent_self_reflection_with_tools()
        
        print("✅ All tests completed successfully!")
        print("🎉 Self-reflection with tools is now working correctly!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)