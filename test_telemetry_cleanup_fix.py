#!/usr/bin/env python3
"""
Test to verify telemetry cleanup fixes work correctly.
This test checks that agents terminate properly without hanging after our cleanup fixes.
"""

import threading
import time
from praisonaiagents import Agent

def test_telemetry_cleanup():
    """Test that telemetry cleanup works correctly and agents don't hang."""
    
    # Record initial thread count
    initial_threads = threading.active_count()
    print(f"Initial thread count: {initial_threads}")
    
    # Create agent
    agent = Agent(
        name="TestAgent",
        role="Test Agent",
        goal="Test telemetry cleanup",
        instructions="Return a simple response"
    )
    
    # Test regular chat completion
    print("Testing regular chat completion...")
    response = agent.chat("Hello", stream=False)
    print(f"Response: {response}")
    
    # Test with self-reflection (to test the paths we fixed)
    print("\nTesting self-reflection path...")
    agent.self_reflect = True
    agent.min_reflect = 1
    agent.max_reflect = 1
    response = agent.chat("What is 2+2?", stream=False)
    print(f"Reflection response: {response}")
    
    # Wait a moment for cleanup
    time.sleep(2)
    
    # Check final thread count
    final_threads = threading.active_count()
    print(f"Final thread count: {final_threads}")
    
    # List all remaining threads for debugging
    remaining_threads = threading.enumerate()
    print(f"Remaining threads: {[t.name for t in remaining_threads]}")
    
    # Check if thread count is reasonable (standardized tolerance)
    thread_difference = final_threads - initial_threads
    if thread_difference <= 2:  # Standardized tolerance
        print("✅ Telemetry cleanup appears to be working correctly")
        return True
    else:
        print(f"❌ Possible thread leak detected: {thread_difference} extra threads")
        print(f"❌ Extra threads: {[t.name for t in remaining_threads if t not in threading.enumerate()[:initial_threads]]}")
        return False

if __name__ == "__main__":
    success = test_telemetry_cleanup()
    if success:
        print("\n✅ All tests passed - telemetry cleanup is working correctly!")
    else:
        print("\n❌ Tests failed - there may be remaining telemetry cleanup issues")