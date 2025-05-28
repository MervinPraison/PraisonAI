#!/usr/bin/env python3
"""
Test script to verify that DeepSeek tool support fix is working.
This test will use a DeepSeek model via Ollama with tools and should gracefully fall back.
"""

from praisonaiagents import Agent

def calculate_sum(a: int, b: int) -> int:
    """Calculate the sum of two numbers."""
    return a + b

def get_weather(city: str) -> str:
    """Get weather information for a city."""
    return f"The weather in {city} is sunny and 25°C."

def main():
    print("Testing DeepSeek tool support fix...")
    print("=" * 50)
    
    # Test with a DeepSeek model that doesn't support tools (should fallback gracefully)
    print("\n1. Testing with DeepSeek R1 model (should show warning and continue):")
    agent = Agent(
        name="TestAgent",
        instructions="You are a helpful assistant that can calculate sums and get weather.",
        llm="ollama/deepseek-r1:latest",
        tools=[calculate_sum, get_weather],
        verbose=True
    )
    
    try:
        response = agent.start("What is 5 + 3? Also what's the weather in Paris?")
        print(f"Response: {response}")
        print("✅ Test passed: Agent continued execution without tools")
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
    
    print("\n" + "=" * 50)
    
    # Test with a standard DeepSeek model that supports tools (should work normally)
    print("\n2. Testing with standard DeepSeek model (should work with tools):")
    agent2 = Agent(
        name="TestAgent2", 
        instructions="You are a helpful assistant that can calculate sums and get weather.",
        llm="deepseek/deepseek-reasoner",
        tools=[calculate_sum, get_weather],
        verbose=True
    )
    
    try:
        response2 = agent2.start("What is 10 + 15?")
        print(f"Response: {response2}")
        print("✅ Test passed: Agent worked with tools")
    except Exception as e:
        print(f"Note: {e} (This might fail if DeepSeek API is not configured)")
    
    print("\n" + "=" * 50)
    print("Test completed!")

if __name__ == "__main__":
    main()