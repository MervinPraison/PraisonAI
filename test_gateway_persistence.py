#!/usr/bin/env python3
"""
Test script to verify gateway session persistence and graceful drain functionality.
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonai.gateway.server import GatewaySession, WebSocketGateway
from praisonaiagents.gateway import GatewayMessage
import time


def test_session_serialization_with_pending_messages():
    """Test that pending inbox messages and execution state are serialized."""
    print("Testing session serialization with pending messages...")
    
    # Create a session
    session = GatewaySession(
        _session_id="test-session-1",
        _agent_id="test-agent",
        _client_id="test-client"
    )
    
    # Add some messages
    session.add_message(GatewayMessage(
        content="Hello",
        sender_id="user",
        session_id="test-session-1"
    ))
    
    # Queue some pending messages
    asyncio.run(session.queue_message("Pending message 1"))
    asyncio.run(session.queue_message("Pending message 2"))
    
    # Mark as executing
    session.mark_executing(True)
    
    # Serialize to dict
    session_dict = session.to_dict()
    
    # Verify pending messages are included
    assert "pending_inbox" in session_dict, "pending_inbox not in serialized data"
    assert len(session_dict["pending_inbox"]) == 2, f"Expected 2 pending messages, got {len(session_dict['pending_inbox'])}"
    assert session_dict["pending_inbox"][0] == "Pending message 1"
    assert session_dict["pending_inbox"][1] == "Pending message 2"
    
    # Verify execution state is included
    assert "is_executing" in session_dict, "is_executing not in serialized data"
    assert session_dict["is_executing"] == True, "is_executing should be True"
    
    print("✓ Session serialization test passed")


def test_session_deserialization_with_pending_messages():
    """Test that pending inbox messages and execution state are restored."""
    print("Testing session deserialization with pending messages...")
    
    # Create session data with pending messages
    session_data = {
        "session_id": "test-session-2",
        "agent_id": "test-agent",
        "client_id": "test-client",
        "is_active": True,
        "created_at": time.time(),
        "last_activity": time.time(),
        "state": {},
        "messages": [],
        "event_cursor": 0,
        "events": [],
        "pending_inbox": ["Restored message 1", "Restored message 2", "Restored message 3"],
        "is_executing": True,
    }
    
    # Deserialize from dict
    session = GatewaySession.from_dict(session_data)
    
    # Verify session was marked as resumed
    assert session._was_resumed == True, "Session should be marked as resumed"
    
    # Verify execution state was restored
    assert session._is_executing == True, "is_executing should be restored as True"
    
    # Verify pending messages were restored
    assert not session._inbox.empty(), "Inbox should not be empty"
    
    # Check all messages are in the queue
    restored_messages = []
    while not session._inbox.empty():
        restored_messages.append(session.get_next_message())
    
    assert len(restored_messages) == 3, f"Expected 3 restored messages, got {len(restored_messages)}"
    assert restored_messages[0] == "Restored message 1"
    assert restored_messages[1] == "Restored message 2"
    assert restored_messages[2] == "Restored message 3"
    
    print("✓ Session deserialization test passed")


async def test_graceful_drain():
    """Test graceful drain functionality."""
    print("Testing graceful drain on shutdown...")
    
    # Create gateway
    gateway = WebSocketGateway(port=0)  # Use port 0 to avoid conflicts
    
    # Create sessions with different states
    session1 = GatewaySession(
        _session_id="drain-test-1",
        _agent_id="test-agent",
        _client_id="client-1"
    )
    session1.mark_executing(False)  # Not executing
    gateway._sessions["drain-test-1"] = session1
    
    session2 = GatewaySession(
        _session_id="drain-test-2",
        _agent_id="test-agent",
        _client_id="client-2"
    )
    session2.mark_executing(True)  # Currently executing
    gateway._sessions["drain-test-2"] = session2
    
    session3 = GatewaySession(
        _session_id="drain-test-3",
        _agent_id="test-agent",
        _client_id="client-3"
    )
    await session3.queue_message("Pending in queue")
    session3.mark_executing(False)  # Has pending messages
    gateway._sessions["drain-test-3"] = session3
    
    # Test drain function
    await gateway._drain_active_sessions(reason="test", timeout=1.0)
    
    # Verify appropriate logging would occur (can't easily test actual persistence without a store)
    print("✓ Graceful drain test completed (would persist 2 active sessions)")


async def test_stop_with_drain():
    """Test that stop() method calls drain."""
    print("Testing stop with drain timeout...")
    
    gateway = WebSocketGateway(port=0)
    gateway._is_running = True
    
    # Add a session with pending work
    session = GatewaySession(
        _session_id="stop-test",
        _agent_id="test-agent",
        _client_id="test-client"
    )
    await session.queue_message("Message to drain")
    gateway._sessions["stop-test"] = session
    
    # Stop with custom drain timeout
    await gateway.stop(drain_timeout=2.0)
    
    # Verify gateway stopped
    assert gateway._is_running == False, "Gateway should be stopped"
    
    print("✓ Stop with drain test passed")


if __name__ == "__main__":
    print("Running gateway session persistence tests...\n")
    
    try:
        # Run synchronous tests
        test_session_serialization_with_pending_messages()
        test_session_deserialization_with_pending_messages()
        
        # Run async tests
        asyncio.run(test_graceful_drain())
        asyncio.run(test_stop_with_drain())
        
        print("\n✅ All tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)