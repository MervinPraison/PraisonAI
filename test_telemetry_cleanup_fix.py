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
    
    # Check if thread count is reasonable (some background threads may remain)
    if final_threads <= initial_threads + 5:  # Allow for some background threads
        print("✅ Telemetry cleanup appears to be working correctly")
        return True
    else:
        print(f"❌ Possible thread leak detected: {final_threads - initial_threads} extra threads")
        return False

if __name__ == "__main__":
    success = test_telemetry_cleanup()
    if success:
        print("\n✅ All tests passed - telemetry cleanup is working correctly!")
    else:
        print("\n❌ Tests failed - there may be remaining telemetry cleanup issues")