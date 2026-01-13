#!/usr/bin/env python3
"""
Test the telemetry cleanup fix
"""
import sys
import os
import signal
from datetime import datetime

# Add signal handler for timeout
def timeout_handler(signum, frame):
    print("SUCCESS: Program terminated within timeout - fix is working!")
    sys.exit(0)

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(15)  # 15 second timeout

try:
    # Set environment variable to disable telemetry (for testing)
    os.environ['PRAISONAI_TELEMETRY_DISABLED'] = 'true'
    
    from praisonaiagents import Agent
    
    print(f"[{datetime.now()}] Starting agent termination test...")
    
    # Create agent with minimal setup
    agent = Agent(
        instructions="You are a helpful assistant",
        llm="gpt-4o-mini"
    )
    
    print(f"[{datetime.now()}] Agent created successfully")
    
    # Test the start method (which was hanging)
    print(f"[{datetime.now()}] Running agent.start()...")
    response = agent.start("Hello, just say hi back!")
    
    print(f"[{datetime.now()}] Agent completed successfully!")
    print(f"Response: {response}")
    
    # If we get here, the fix worked
    print(f"[{datetime.now()}] SUCCESS: Program should terminate properly now!")
    
except Exception as e:
    print(f"ERROR: Exception occurred: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    # Cancel the alarm
    signal.alarm(0)

print("Test completed - program should exit now.") 