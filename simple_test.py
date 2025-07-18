#!/usr/bin/env python3
"""
Simple test to verify the termination fix
"""
import sys
import os

# Add the src directory to the path so we can import praisonaiagents
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

print("Testing agent termination fix...")

try:
    from praisonaiagents import Agent
    
    # Create agent with minimal setup
    agent = Agent(instructions="You are a helpful AI assistant")
    
    # Run the same test as in the issue
    print("Running agent.start() ...")
    response = agent.start("Write a movie script about a robot on Mars")
    
    print("Agent completed successfully!")
    print(f"Response type: {type(response)}")
    print(f"Response length: {len(str(response)) if response else 'None'}")
    
    # If we get here, the fix worked
    print("SUCCESS: Program should terminate properly!")
    
except Exception as e:
    print(f"ERROR: Exception occurred: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("Test completed - program should exit now.")