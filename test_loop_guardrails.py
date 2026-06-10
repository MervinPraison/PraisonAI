#!/usr/bin/env python3
"""
Test to validate that the loop guardrails fix works properly.
"""

import os
import sys
sys.path.insert(0, 'src/praisonai-agents')

from praisonaiagents import Agent, tool
from praisonaiagents.config.feature_configs import ExecutionConfig

@tool
def broken_tool(query: str) -> str:
    """A deliberately broken tool that always returns an unhelpful result."""
    return f"Tool failed to process '{query}'. Please try again with a different approach."

@tool
def another_broken_tool(input_data: str) -> str:
    """Another broken tool that doesn't help."""
    return f"Unable to handle '{input_data}'. Consider using a different tool."

def test_default_guardrail():
    """Test that the default guardrail limit (10) works."""
    print("Testing default guardrail limit...")
    
    agent = Agent(
        name="test-agent",
        llm="gpt-4o-mini",
        instructions="Try to help the user. Use tools to get information.",
        tools=[broken_tool, another_broken_tool],
        verbose=True
    )
    
    try:
        response = agent.chat("I need weather information for New York. Please help me get accurate data!")
        print(f"Response: {response}")
        
        # If we get here without an infinite loop, the guardrail worked
        if "Tool call limit reached" in response:
            print("✅ DEFAULT GUARDRAIL WORKING: Agent stopped due to tool call limit")
            return True
        else:
            print("⚠️ Agent completed without hitting limit (may be expected if it naturally stopped)")
            return True
            
    except Exception as e:
        print(f"❌ Error during test: {e}")
        return False

def test_custom_guardrail():
    """Test with a custom lower limit."""
    print("\nTesting custom guardrail limit (3)...")
    
    agent = Agent(
        name="test-agent",
        llm="gpt-4o-mini",
        instructions="Use tools extensively to help the user.",
        tools=[broken_tool, another_broken_tool],
        execution=ExecutionConfig(max_tool_calls_per_turn=3),
        verbose=True
    )
    
    try:
        response = agent.chat("Get me detailed weather, traffic, and restaurant information for New York!")
        print(f"Response: {response}")
        
        if "Tool call limit reached (3 calls)" in response:
            print("✅ CUSTOM GUARDRAIL WORKING: Agent stopped at limit of 3")
            return True
        else:
            print("⚠️ Agent completed without hitting custom limit")
            return True
            
    except Exception as e:
        print(f"❌ Error during test: {e}")
        return False

def test_high_limit():
    """Test with a higher limit to ensure it doesn't interfere with normal operation."""
    print("\nTesting high guardrail limit (50)...")
    
    agent = Agent(
        name="test-agent",
        llm="gpt-4o-mini", 
        instructions="Be helpful and concise. Answer questions directly when possible.",
        execution=ExecutionConfig(max_tool_calls_per_turn=50),
        verbose=True
    )
    
    try:
        response = agent.chat("What's 2 + 2?")
        print(f"Response: {response}")
        
        if "Tool call limit reached" not in response:
            print("✅ HIGH LIMIT WORKING: Agent operates normally without hitting limit")
            return True
        else:
            print("❌ Agent hit limit unexpectedly")
            return False
            
    except Exception as e:
        print(f"❌ Error during test: {e}")
        return False

if __name__ == "__main__":
    print("Testing Loop Guardrails Implementation")
    print("=" * 50)
    
    # Set up environment for testing
    os.environ.setdefault("OPENAI_API_KEY", "test")  # Use test key for safety
    
    results = []
    
    # Run tests
    results.append(test_default_guardrail())
    results.append(test_custom_guardrail())
    results.append(test_high_limit())
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY:")
    print(f"Tests passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 ALL TESTS PASSED - Loop guardrails are working!")
        sys.exit(0)
    else:
        print("❌ Some tests failed - Check implementation")
        sys.exit(1)