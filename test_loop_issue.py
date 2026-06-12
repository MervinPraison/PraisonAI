#!/usr/bin/env python3
"""
Test to validate the loop guardrails issue in agent.chat().
This script tests if agent.chat() can get stuck in an infinite loop with broken tools.
"""

from praisonaiagents import Agent, tool
import sys

@tool
def broken_weather_tool(location: str) -> str:
    """Get weather information for a location. This tool is intentionally broken and always returns the same unhelpful result."""
    return f"Weather data unavailable for {location}. Please try again with a different tool."

@tool 
def another_broken_tool(query: str) -> str:
    """Search for information. Also broken and unhelpful."""
    return f"No results found for '{query}'. Please try a different search."

def test_loop_vulnerability():
    """Test if agent.chat() can get stuck in a loop with broken tools."""
    
    print("Testing loop vulnerability in agent.chat()...")
    
    agent = Agent(
        name="test-agent",
        llm="gpt-4o-mini",  # Fast model for testing
        instructions="You are a helpful assistant. Always try to fulfill user requests using available tools.",
        tools=[broken_weather_tool, another_broken_tool]
    )
    
    # Track tool calls
    call_count = 0
    original_execute_tool = agent.execute_tool
    
    def counting_execute_tool(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        print(f"Tool call #{call_count}: {args[0] if args else 'unknown'}")
        
        # Safety valve - prevent actual infinite loop in test
        if call_count > 10:
            print("🚨 SAFETY VALVE TRIGGERED: Too many tool calls!")
            raise RuntimeError("Safety valve triggered: too many tool calls")
            
        return original_execute_tool(*args, **kwargs)
    
    agent.execute_tool = counting_execute_tool
    
    try:
        response = agent.chat("What's the weather like in New York? I really need this information!")
        print(f"\nFinal response: {response}")
        print(f"Total tool calls: {call_count}")
        
        if call_count > 5:
            print("❌ ISSUE CONFIRMED: Agent made excessive tool calls without guardrails")
            return True
        else:
            print("✅ Agent stopped within reasonable limits")
            return False
            
    except Exception as e:
        print(f"Error during test: {e}")
        print(f"Tool calls before error: {call_count}")
        return call_count > 5

if __name__ == "__main__":
    issue_exists = test_loop_vulnerability()
    sys.exit(1 if issue_exists else 0)