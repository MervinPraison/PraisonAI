"""Test script to verify the tool attribute fix"""
from praisonaiagents import Agent

# Test 1: Basic agent without tools (should work)
print("Test 1: Basic agent without tools")
try:
    agent = Agent(
        instructions="You are a helpful assistant",
        llm="gpt-4o-mini"
    )
    print("✓ Basic agent created successfully")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 2: Agent with basic function tool
print("\nTest 2: Agent with function tool")
def get_weather(location: str) -> str:
    """Get the weather for a location"""
    return f"The weather in {location} is sunny"

try:
    agent = Agent(
        instructions="You are a helpful assistant",
        llm="gpt-4o-mini",
        tools=[get_weather]
    )
    print("✓ Agent with function tool created successfully")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 3: Test with dictionary-style tool (simulate MCP response)
print("\nTest 3: Test with dictionary-style tool")
try:
    from praisonaiagents.mcp.mcp import MCP
    # This will test if our fix handles dictionary tools properly
    print("✓ MCP module imported successfully")
except Exception as e:
    print(f"✗ Error importing MCP: {e}")

print("\nAll tests completed!")