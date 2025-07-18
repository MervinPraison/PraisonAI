#!/usr/bin/env python3
"""
Test to specifically check for telemetry thread cleanup and prevent hanging.
This test simulates the scenario where telemetry threads could cause hanging.
"""

import threading
import time
import sys
import os

# Set a fake API key to avoid errors
os.environ['OPENAI_API_KEY'] = 'test-key-for-cleanup-test'
os.environ['OPENAI_API_BASE'] = 'http://localhost:1234/v1'

def test_thread_cleanup():
    """Test that no telemetry threads remain after cleanup."""
    
    print(f"Initial thread count: {threading.active_count()}")
    initial_threads = set(threading.enumerate())
    
    # Import and use telemetry
    from praisonaiagents.telemetry.telemetry import get_telemetry, force_shutdown_telemetry
    
    # Get telemetry instance (this might start background threads)
    telemetry = get_telemetry()
    
    # Track some events to potentially start background threads
    telemetry.track_agent_execution("test_agent", success=True)
    telemetry.track_tool_usage("test_tool", success=True)
    telemetry.flush()
    
    # Wait a moment for threads to start
    time.sleep(0.5)
    
    after_telemetry_threads = set(threading.enumerate())
    new_threads = after_telemetry_threads - initial_threads
    
    print(f"After telemetry initialization: {threading.active_count()} threads")
    if new_threads:
        print(f"New threads created: {[t.name for t in new_threads]}")
    
    # Now force cleanup
    print("Forcing telemetry cleanup...")
    force_shutdown_telemetry()
    
    # Wait for cleanup to complete
    time.sleep(1)
    
    final_threads = set(threading.enumerate())
    remaining_new_threads = final_threads - initial_threads
    
    print(f"Final thread count: {threading.active_count()}")
    print(f"Final threads: {[t.name for t in final_threads]}")
    
    if remaining_new_threads:
        print(f"❌ Threads still remaining after cleanup: {[t.name for t in remaining_new_threads]}")
        return False
    else:
        print("✅ All telemetry threads cleaned up successfully")
        return True

def test_agent_cleanup():
    """Test that agent cleanup works properly."""
    
    from praisonaiagents import Agent
    
    initial_threads = threading.active_count()
    print(f"Initial thread count before agent: {initial_threads}")
    
    # Create agent
    agent = Agent(
        name="TestAgent",
        role="Test Agent", 
        goal="Test cleanup",
        instructions="Test"
    )
    
    after_agent_threads = threading.active_count()
    print(f"Thread count after agent creation: {after_agent_threads}")
    
    # Force cleanup
    agent._cleanup_telemetry()
    
    # Wait for cleanup
    time.sleep(0.5)
    
    final_threads = threading.active_count()
    print(f"Final thread count after agent cleanup: {final_threads}")
    
    if final_threads <= initial_threads + 1:  # Allow for some variance
        print("✅ Agent cleanup successful")
        return True
    else:
        print(f"❌ Agent cleanup may have left threads: {final_threads - initial_threads} extra")
        return False

if __name__ == "__main__":
    print("Testing thread cleanup to prevent hanging...")
    
    test1 = test_thread_cleanup()
    print()
    test2 = test_agent_cleanup()
    
    if test1 and test2:
        print("\n✅ All thread cleanup tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some thread cleanup tests failed!")
        sys.exit(1)