#!/usr/bin/env python3

"""
Test script for the streaming fix implementation
"""

import sys
import os

# Add the src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents import Agent

def test_streaming():
    print("Testing streaming functionality...")
    
    # Create agent with streaming enabled - use a simpler test without API calls
    agent = Agent(
        instructions="You are a helpful assistant",
        llm="mock",  # Use mock model for testing
        self_reflect=False,
        verbose=False,
        stream=True
    )
    
    # Test the streaming functionality
    print("Testing streaming with short response...")
    prompt = "Write a short sentence about the weather"
    
    # Test if start() returns a generator when streaming
    result = agent.start(prompt)
    print(f"Type of result: {type(result)}")
    
    if hasattr(result, '__iter__') and not isinstance(result, str):
        print("Success! Result is iterable (generator)")
        print("The streaming implementation is working correctly")
    else:
        print("Result is not iterable - this means streaming is not working")
        print(f"Result: {result}")

def test_backward_compatibility():
    print("\nTesting backward compatibility...")
    
    # Test with streaming disabled
    agent = Agent(
        instructions="You are a helpful assistant",
        llm="mock",
        self_reflect=False,
        verbose=False,
        stream=False
    )
    
    result = agent.start("Say hello", stream=False)
    print(f"Type of result with stream=False: {type(result)}")
    
    # Test with streaming enabled but stream=False in start()
    agent2 = Agent(
        instructions="You are a helpful assistant",
        llm="mock",
        self_reflect=False,
        verbose=False,
        stream=True
    )
    
    result2 = agent2.start("Say hello", stream=False)
    print(f"Type of result with agent.stream=True but start(stream=False): {type(result2)}")

if __name__ == "__main__":
    test_streaming()
    test_backward_compatibility()