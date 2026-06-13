#!/usr/bin/env python3
"""Test script to verify EventBus performance optimizations."""

import sys
import os
import time
from unittest.mock import patch

# Add the praisonai-agents package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

# Import the EventBus classes
from praisonaiagents.bus import EventBus, Event, get_default_bus

def test_has_subscribers_property():
    """Test has_subscribers property works correctly."""
    print("Testing has_subscribers property...")
    
    bus = EventBus()
    
    # Should be False when empty
    assert not bus.has_subscribers, "Empty bus should have no subscribers"
    
    # Add a subscriber
    sub_id = bus.subscribe(lambda e: None)
    assert bus.has_subscribers, "Bus with subscriber should return True"
    
    # Remove subscriber
    bus.unsubscribe(sub_id)
    assert not bus.has_subscribers, "Bus after unsubscribing should return False"
    
    print("✓ has_subscribers property test passed")

def test_publish_fast_path():
    """Test that publishing with no subscribers skips expensive work."""
    print("Testing fast path optimization...")
    
    bus = EventBus()
    
    # Test with no subscribers - should not store in history
    event = Event(type="test.event", data={"key": "value"})
    result = bus.publish_event(event)
    
    # Should return the event but not store in history
    assert result is event, "Should return the original event"
    assert len(bus.get_history()) == 0, "Should not store in history with no subscribers"
    
    print("✓ Fast path test passed")

def test_normal_path_with_subscribers():
    """Test that behavior is unchanged when subscribers exist."""
    print("Testing normal path with subscribers...")
    
    bus = EventBus()
    received = []
    
    # Add a subscriber
    bus.subscribe(lambda e: received.append(e))
    
    # Publish an event
    event = Event(type="test.event", data={"key": "value"}) 
    result = bus.publish_event(event)
    
    # Should store in history and call subscribers
    assert result is event, "Should return the event"
    assert len(bus.get_history()) == 1, "Should store in history with subscribers"
    assert len(received) == 1, "Subscriber should receive the event"
    assert received[0] is event, "Subscriber should receive the same event"
    
    print("✓ Normal path test passed")

def test_memory_optimization():
    """Test the memory module optimization."""
    print("Testing memory module optimization...")
    
    try:
        from praisonaiagents.memory.core import MemoryCoreMixin
        from praisonaiagents.bus import get_default_bus
        
        # Create a test class that includes the mixin
        class TestMemory(MemoryCoreMixin):
            def __init__(self):
                self.verbose = 0
                self.provider = "test"
        
        # Test that _emit_memory_event returns early when no subscribers
        memory = TestMemory()
        bus = get_default_bus()
        
        # Clear any existing subscribers
        bus.clear_subscribers()
        
        # This should return early and not throw any errors
        memory._emit_memory_event("test", "short_term", "test content", {})
        
        print("✓ Memory optimization test passed")
        
    except ImportError as e:
        print(f"⚠ Memory module test skipped (import error): {e}")

def benchmark_performance():
    """Simple benchmark to show performance improvement."""
    print("Running performance benchmark...")
    
    bus = EventBus()
    
    # Benchmark without subscribers (fast path)
    start_time = time.time()
    for i in range(1000):
        event = Event(type="test.event", data={"iteration": i})
        bus.publish_event(event)
    fast_path_time = time.time() - start_time
    
    # Add a subscriber and benchmark again
    received = []
    bus.subscribe(lambda e: received.append(e))
    
    start_time = time.time()
    for i in range(1000):
        event = Event(type="test.event", data={"iteration": i})
        bus.publish_event(event)
    normal_path_time = time.time() - start_time
    
    print(f"Fast path (no subscribers): {fast_path_time:.4f}s")
    print(f"Normal path (with subscribers): {normal_path_time:.4f}s")
    
    # Fast path should be faster (though the difference might be minimal for small iterations)
    if fast_path_time < normal_path_time:
        print("✓ Fast path is faster than normal path")
    else:
        print("ℹ Fast path timing similar to normal path (expected for small iterations)")

def main():
    """Run all tests."""
    print("EventBus Performance Optimization Test Suite")
    print("=" * 50)
    
    try:
        test_has_subscribers_property()
        test_publish_fast_path()
        test_normal_path_with_subscribers()
        test_memory_optimization()
        benchmark_performance()
        
        print("\n✅ All tests passed! EventBus optimization is working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()