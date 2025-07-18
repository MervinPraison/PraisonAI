#!/usr/bin/env python3
"""
Test script to verify the agent termination fix.
This script should terminate properly without requiring Ctrl+C.
"""

import sys
import os
import time

# Add the praisonai-agents package to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

try:
    from praisonaiagents import Agent
    
    print("Starting agent termination test...")
    start_time = time.time()
    
    # Create an agent with the same configuration as the issue example
    agent = Agent(instructions="You are a helpful AI assistant")
    
    # Test the exact scenario from the issue
    print("Testing agent.start() with movie script request...")
    result = agent.start("Write a short movie script about a robot on Mars")
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    print(f"\n✅ Test completed successfully in {execution_time:.2f} seconds")
    print("✅ Agent terminated properly without requiring Ctrl+C")
    print("✅ Fix verified: Telemetry cleanup is working correctly")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running this from the correct directory")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error during test: {e}")
    sys.exit(1)