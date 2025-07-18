#!/usr/bin/env python3
"""
Test script to verify the termination fix works
"""
import sys
import os
import signal

# Add the src directory to the path so we can import praisonaiagents
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

# Set up timeout mechanism (Unix systems only)
def timeout_handler(signum, frame):
    print("ERROR: Test timed out - program is still hanging!")
    sys.exit(1)

# Set up signal handler for timeout (Unix systems only)
if sys.platform != "win32":
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(30)  # 30 second timeout

try:
    # Import here to avoid issues with path setup
    from praisonaiagents import Agent
    
    print("Testing agent termination fix...")
    
    # Create agent with minimal setup
    agent = Agent(instructions="You are a helpful AI assistant")
    
    # Run the same test as in the issue
    print("Running agent.start() ...")
    response = agent.start("Write a short hello world message")
    
    print("Agent completed successfully!")
    print(f"Response (truncated): {str(response)[:100]}...")
    
    # If we get here, the fix worked
    print("SUCCESS: Program terminated properly without hanging!")
    
except Exception as e:
    print(f"ERROR: Exception occurred: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    # Cancel the alarm (Unix systems only)
    if sys.platform != "win32":
        signal.alarm(0)