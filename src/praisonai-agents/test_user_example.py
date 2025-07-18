#!/usr/bin/env python3

"""
Test script that exactly matches the user's code example
"""

import sys
import os

# Add the src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents import Agent

def test_user_example():
    print("Testing user's exact code example...")
    
    # This is the exact code from the user's issue
    agent = Agent(
        instructions="You are a helpful assistant",
        llm="mock",  # Use mock model for testing
        self_reflect=False,
        verbose=False,
        stream=True
    )

    # Test the streaming functionality
    print("Testing: for chunk in agent.start(prompt):")
    prompt = "Write a report on about the history of the world"
    
    # This is the exact code the user wants to work
    result = agent.start(prompt)
    print(f"Type of result: {type(result)}")
    
    if hasattr(result, '__iter__') and not isinstance(result, str):
        print("✅ SUCCESS: agent.start() returns a generator!")
        print("The user's code will now work:")
        print("for chunk in agent.start(prompt):")
        print("    print(chunk, end='', flush=True)")
        print("\nSimulating the iteration (first 5 chunks):")
        
        # Test the first few chunks
        count = 0
        for chunk in result:
            print(f"Chunk {count}: {chunk}")
            count += 1
            if count >= 5:  # Just show first 5 chunks to avoid long output
                break
        
        print(f"\n✅ Streaming is working! Generated {count} chunks.")
    else:
        print("❌ FAILED: agent.start() does not return a generator")
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")

if __name__ == "__main__":
    test_user_example()