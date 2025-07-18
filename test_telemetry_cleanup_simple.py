#!/usr/bin/env python3
"""
Simple test to verify telemetry cleanup fixes work correctly.
This test focuses on the cleanup functionality without requiring OpenAI API calls.
"""

import os
import threading
import time
import sys
import logging

# Set up logging to see debug info
logging.basicConfig(level=logging.DEBUG)

# Set a fake API key to avoid errors
os.environ['OPENAI_API_KEY'] = 'test-key-for-cleanup-test'
os.environ['OPENAI_API_BASE'] = 'http://localhost:1234/v1'

def test_telemetry_cleanup_direct():
    """Test that telemetry cleanup works correctly by directly testing the cleanup functions."""
    
    # Record initial thread count
    initial_threads = threading.active_count()
    print(f"Initial thread count: {initial_threads}")
    
    # Test the telemetry cleanup function directly
    try:
        from praisonaiagents.telemetry.telemetry import get_telemetry, force_shutdown_telemetry
        
        # Get a telemetry instance
        telemetry = get_telemetry()
        print(f"Telemetry enabled: {telemetry.enabled}")
        
        # Check if PostHog is initialized
        if hasattr(telemetry, '_posthog') and telemetry._posthog:
            print("PostHog client initialized")
        else:
            print("PostHog client not initialized")
        
        # Test cleanup
        print("Testing force_shutdown_telemetry()...")
        force_shutdown_telemetry()
        
        # Wait a moment for cleanup
        time.sleep(1)
        
        # Check final thread count
        final_threads = threading.active_count()
        print(f"Final thread count: {final_threads}")
        
        # List remaining threads
        remaining_threads = threading.enumerate()
        print(f"Remaining threads: {[t.name for t in remaining_threads]}")
        
        # Check if cleanup was successful
        thread_difference = final_threads - initial_threads
        if thread_difference <= 2:  # Standardized tolerance
            print("✅ Telemetry cleanup appears to be working correctly")
            return True
        else:
            print(f"❌ Possible thread leak detected: {thread_difference} extra threads")
            print(f"❌ Extra threads: {[t.name for t in remaining_threads if t not in threading.enumerate()[:initial_threads]]}")
            return False
            
    except Exception as e:
        print(f"❌ Error during telemetry cleanup test: {e}")
        return False

def test_agent_cleanup_method():
    """Test that the agent cleanup method works correctly."""
    
    try:
        from praisonaiagents import Agent
        
        # Create agent
        agent = Agent(
            name="TestAgent",
            role="Test Agent",
            goal="Test telemetry cleanup",
            instructions="Return a simple response"
        )
        
        # Test the cleanup method directly
        print("Testing agent._cleanup_telemetry()...")
        agent._cleanup_telemetry()
        
        print("✅ Agent cleanup method executed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error during agent cleanup test: {e}")
        return False

if __name__ == "__main__":
    print("Testing telemetry cleanup fixes...")
    
    # Test 1: Direct telemetry cleanup
    print("\n=== Test 1: Direct telemetry cleanup ===")
    test1_success = test_telemetry_cleanup_direct()
    
    # Test 2: Agent cleanup method
    print("\n=== Test 2: Agent cleanup method ===")
    test2_success = test_agent_cleanup_method()
    
    # Final result
    if test1_success and test2_success:
        print("\n✅ All tests passed - telemetry cleanup is working correctly!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed - there may be remaining telemetry cleanup issues")
        sys.exit(1)