#!/usr/bin/env python3

"""
Test script to verify streaming functionality works for Agent.start() method
"""

import sys
import os

# Add the package to Python path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

from praisonaiagents import Agent

def test_streaming():
    """Test streaming functionality"""
    print("Testing streaming functionality...")
    
    # Create agent with streaming enabled
    agent = Agent(
        instructions="You are a helpful assistant",
        llm="gpt-3.5-turbo",  # Use a basic model for testing
        self_reflect=False,
        verbose=False,
        stream=True
    )
    
    print("\n=== Testing Agent.start() with streaming ===")
    try:
        # Test streaming - should return a generator
        result = agent.start("Write a short poem about cats")
        
        if hasattr(result, '__iter__') and not isinstance(result, str):
            print("✅ Agent.start() returned a generator")
            print("Chunks received:")
            for i, chunk in enumerate(result):
                print(f"Chunk {i+1}: '{chunk}'")
                if i > 10:  # Limit output for testing
                    print("... (truncated)")
                    break
        else:
            print(f"❌ Agent.start() returned: {type(result)} instead of generator")
            print(f"Result: {result}")
    except Exception as e:
        print(f"❌ Error in streaming test: {e}")
    
    print("\n=== Testing Agent.start() without streaming ===")
    try:
        # Test non-streaming - should return a string
        result = agent.start("Hello", stream=False)
        
        if isinstance(result, str):
            print("✅ Agent.start() with stream=False returned a string")
            print(f"Result: {result[:100]}...")
        else:
            print(f"❌ Agent.start() with stream=False returned: {type(result)}")
    except Exception as e:
        print(f"❌ Error in non-streaming test: {e}")

if __name__ == "__main__":
    test_streaming()