#!/usr/bin/env python3
"""
Test script to verify the type casting fix for tool arguments.
"""
import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_tool(number: int, text: str, flag: bool = False):
    """Test tool that expects specific types"""
    print(f"Received: number={number} (type: {type(number)}), text={text} (type: {type(text)}), flag={flag} (type: {type(flag)})")
    assert isinstance(number, int), f"Expected int, got {type(number)}"
    assert isinstance(text, str), f"Expected str, got {type(text)}"
    assert isinstance(flag, bool), f"Expected bool, got {type(flag)}"
    return {"success": True, "number": number, "text": text, "flag": flag}

def main():
    from praisonaiagents.agent.agent import Agent
    
    # Create an agent with our test tool
    agent = Agent(
        name="Test Agent",
        role="Tester",
        goal="Test type casting",
        tools=[test_tool]
    )
    
    # Test case 1: Arguments as they would come from JSON (strings for integers)
    print("Test 1: Integer as string")
    arguments = {"number": "42", "text": "hello", "flag": "true"}
    result = agent.execute_tool("test_tool", arguments)
    print(f"Result: {result}")
    print()
    
    # Test case 2: Mixed types
    print("Test 2: Mixed types")
    arguments = {"number": 123.0, "text": "world", "flag": "false"}
    result = agent.execute_tool("test_tool", arguments)
    print(f"Result: {result}")
    print()
    
    # Test case 3: Already correct types
    print("Test 3: Correct types")
    arguments = {"number": 99, "text": "test", "flag": True}
    result = agent.execute_tool("test_tool", arguments)
    print(f"Result: {result}")
    print()
    
    print("All tests passed! Type casting is working correctly.")

if __name__ == "__main__":
    main()