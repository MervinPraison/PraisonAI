#!/usr/bin/env python3
"""
Integration tests for message steering capability.

Tests the real-time message steering implementation including
real agentic tests with actual LLM calls.
"""
import time
import threading
import pytest
from praisonaiagents import Agent


def test_message_steering_basic():
    """Test basic message steering functionality."""
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


def test_message_steering_disabled():
    """Test that steering is disabled by default."""
    agent = Agent(name="test_agent", instructions="You are helpful")
    
    # Verify steering is disabled
    assert not agent.message_steering_enabled, "Message steering should be disabled by default"
    
    # Test steering call returns empty ID
    msg_id = agent.steer("This should be ignored")
    assert msg_id == "", "Should return empty string when disabled"
    
    status = agent.get_steering_status()
    assert not status["enabled"], "Steering should be disabled"
    assert status["pending_count"] == 0, "Should have no pending messages"


def test_message_steering_integration():
    """Test integration with execution (smoke test only - no actual LLM call)."""
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


def test_message_steering_live_execution():
    """Test steering injection during live LLM execution (MANDATORY real agentic test)."""
    agent = Agent(
        name="steering_live_test",
        instructions="You are a helpful assistant. Always acknowledge user guidance when provided.",
        message_steering=True,
        llm="gpt-4o-mini"
    )
    
    # Container to capture agent response
    result_container = {}
    
    def run_agent():
        """Execute agent in background thread."""
        try:
            result = agent.start("Explain quantum computing in detail")
            result_container["response"] = result
            result_container["success"] = True
        except Exception as e:
            result_container["error"] = str(e)
            result_container["success"] = False
    
    # Start agent execution in background
    thread = threading.Thread(target=run_agent)
    thread.start()
    
    # Allow execution to start
    time.sleep(0.5)
    
    # Send steering message while agent is running
    msg_id = agent.steer("Keep your explanation under 100 words and focus on practical applications", priority=10)
    assert msg_id, "Should queue steering message"
    
    # Wait for execution to complete (with timeout)
    thread.join(timeout=30)
    
    # Verify execution completed successfully
    assert result_container.get("success", False), f"Agent execution failed: {result_container.get('error', 'Unknown error')}"
    
    response = result_container.get("response", "")
    assert response, "Should return non-empty response from LLM"
    assert len(response) > 10, "Response should be substantial"
    
    # Print response for manual verification
    print(f"\n🤖 Agent Response:\n{response}")
    
    # Verify steering status after execution
    final_status = agent.get_steering_status()
    # Note: Message may have been processed during execution
    print(f"\n📊 Final steering status: {final_status}")


def test_message_steering_priority_handling():
    """Test different priority levels for steering messages."""
    agent = Agent(
        name="priority_test",
        instructions="You are helpful",
        message_steering=True
    )
    
    # Test different priority levels
    low_msg = agent.steer("Low priority guidance", priority=1)
    normal_msg = agent.steer("Normal priority guidance", priority=5) 
    high_msg = agent.steer("High priority guidance", priority=10)
    urgent_msg = agent.steer("Urgent guidance", priority=20)
    interrupt_msg = agent.steer("Interrupt guidance", priority=30)
    
    # All should return message IDs
    assert all([low_msg, normal_msg, high_msg, urgent_msg, interrupt_msg])
    
    # Check pending count
    status = agent.get_steering_status()
    assert status["pending_count"] == 5
    
    # Process one message
    steering_msg = agent._check_steering_messages()
    # Should process highest priority first
    assert steering_msg is not None
    assert "Interrupt" in steering_msg or "Urgent" in steering_msg


if __name__ == "__main__":
    # Run tests manually if executed directly
    pytest.main([__file__, "-v"])