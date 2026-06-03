#!/usr/bin/env python3
"""
Test script for message steering capability.

This tests the real-time message steering implementation.
"""
import sys
import os
import time
import threading

# Add the package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

try:
    from praisonaiagents import Agent
    
    def test_message_steering_basic():
        """Test basic message steering functionality."""
        print("Testing basic message steering...")
        
        # Create agent with message steering enabled
        agent = Agent(
            name="test_agent",
            instructions="You are a helpful assistant. Acknowledge any user guidance.",
            message_steering=True,
            llm="gpt-4o-mini"
        )
        
        # Verify steering is enabled
        assert agent.message_steering_enabled, "Message steering should be enabled"
        
        # Test queueing messages
        msg_id = agent.steer("Focus on being concise")
        assert msg_id, "Should return message ID"
        
        status = agent.get_steering_status()
        assert status["enabled"], "Steering should be enabled"
        assert status["pending_count"] > 0, "Should have pending messages"
        
        print("✅ Basic message steering test passed")
        return True
        
    def test_message_steering_disabled():
        """Test that steering is disabled by default."""
        print("Testing disabled message steering...")
        
        agent = Agent(name="test_agent", instructions="You are helpful")
        
        # Verify steering is disabled
        assert not agent.message_steering_enabled, "Message steering should be disabled by default"
        
        # Test steering call returns empty ID
        msg_id = agent.steer("This should be ignored")
        assert msg_id == "", "Should return empty string when disabled"
        
        status = agent.get_steering_status()
        assert not status["enabled"], "Steering should be disabled"
        assert status["pending_count"] == 0, "Should have no pending messages"
        
        print("✅ Disabled message steering test passed")
        return True
        
    def test_message_steering_integration():
        """Test integration with execution (smoke test only - no actual LLM call)."""
        print("Testing message steering integration...")
        
        agent = Agent(
            name="integration_test",
            instructions="You are helpful",
            message_steering=True
        )
        
        # Add a steering message
        msg_id = agent.steer("Please be very brief", priority=10)
        assert msg_id, "Should queue message"
        
        # Check that steering check method exists
        assert hasattr(agent, '_check_steering_messages'), "Should have steering check method"
        
        # Test the steering check method
        steering_msg = agent._check_steering_messages()
        assert steering_msg is not None, "Should return steering message"
        assert "USER GUIDANCE" in steering_msg, "Should format as guidance"
        assert "brief" in steering_msg.lower(), "Should contain original message"
        
        print("✅ Integration test passed")
        return True
    
    def run_all_tests():
        """Run all message steering tests."""
        print("Running message steering tests...\n")
        
        tests = [
            test_message_steering_basic,
            test_message_steering_disabled, 
            test_message_steering_integration
        ]
        
        passed = 0
        for test_func in tests:
            try:
                if test_func():
                    passed += 1
            except Exception as e:
                print(f"❌ {test_func.__name__} failed: {e}")
        
        print(f"\n✅ {passed}/{len(tests)} tests passed")
        
        if passed == len(tests):
            print("🎉 All message steering tests passed!")
            return True
        else:
            print("❌ Some tests failed")
            return False
            
    if __name__ == "__main__":
        success = run_all_tests()
        sys.exit(0 if success else 1)
        
except Exception as e:
    print(f"❌ Failed to import or run tests: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)