"""Tests for MCP Resumability - TDD approach.

These tests define the expected behavior of SSE stream resumability
per MCP Protocol Revision 2025-11-25.

Resumability features:
- SSE event ID tracking
- Last-Event-ID header support
- Message replay on reconnection
- Retry field handling
"""

import pytest


class TestResumabilityManager:
    """Test ResumabilityManager class."""
    
    def test_manager_creation(self):
        """Test ResumabilityManager can be created."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        assert manager.get_retry_delay() == 3000  # Default 3 seconds
    
    def test_set_and_get_last_event_id(self):
        """Test setting and getting last event ID for a stream."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        
        # Initially no event ID
        assert manager.get_last_event_id("stream-1") is None
        
        # Set event ID
        manager.set_last_event_id("stream-1", "event-123")
        assert manager.get_last_event_id("stream-1") == "event-123"
    
    def test_multiple_streams(self):
        """Test tracking multiple streams independently."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        
        manager.set_last_event_id("stream-1", "event-a")
        manager.set_last_event_id("stream-2", "event-b")
        
        assert manager.get_last_event_id("stream-1") == "event-a"
        assert manager.get_last_event_id("stream-2") == "event-b"
    
    def test_update_event_id(self):
        """Test updating event ID for a stream."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        
        manager.set_last_event_id("stream-1", "event-1")
        manager.set_last_event_id("stream-1", "event-2")
        
        assert manager.get_last_event_id("stream-1") == "event-2"
    
    def test_set_retry_delay(self):
        """Test setting retry delay from SSE retry field."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        
        manager.set_retry_delay(5000)
        assert manager.get_retry_delay() == 5000
    
    def test_get_resume_headers_with_event_id(self):
        """Test getting resume headers when event ID is available."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        manager.set_last_event_id("stream-1", "event-123")
        
        headers = manager.get_resume_headers("stream-1")
        
        assert headers == {'Last-Event-ID': 'event-123'}
    
    def test_get_resume_headers_without_event_id(self):
        """Test getting resume headers when no event ID is stored."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        
        headers = manager.get_resume_headers("stream-1")
        
        assert headers == {}
    
    def test_clear_stream(self):
        """Test clearing tracking for a specific stream."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        manager.set_last_event_id("stream-1", "event-a")
        manager.set_last_event_id("stream-2", "event-b")
        
        manager.clear_stream("stream-1")
        
        assert manager.get_last_event_id("stream-1") is None
        assert manager.get_last_event_id("stream-2") == "event-b"
    
    def test_clear_all(self):
        """Test clearing all stream tracking."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        manager.set_last_event_id("stream-1", "event-a")
        manager.set_last_event_id("stream-2", "event-b")
        
        manager.clear_all()
        
        assert manager.get_last_event_id("stream-1") is None
        assert manager.get_last_event_id("stream-2") is None


class TestSSEEventParsing:
    """Test SSE event parsing utilities."""
    
    def test_parse_sse_event_with_id(self):
        """Test parsing SSE event with ID field."""
        from praisonaiagents.mcp.mcp_session import parse_sse_event
        
        event_text = "id: event-123\ndata: {\"test\": 1}\n\n"
        event = parse_sse_event(event_text)
        
        assert event['id'] == 'event-123'
        assert event['data'] == '{"test": 1}'
    
    def test_parse_sse_event_with_retry(self):
        """Test parsing SSE event with retry field."""
        from praisonaiagents.mcp.mcp_session import parse_sse_event
        
        event_text = "retry: 5000\ndata: {}\n\n"
        event = parse_sse_event(event_text)
        
        assert event['retry'] == 5000
    
    def test_parse_sse_event_data_only(self):
        """Test parsing SSE event with only data."""
        from praisonaiagents.mcp.mcp_session import parse_sse_event
        
        event_text = "data: {\"message\": \"hello\"}\n\n"
        event = parse_sse_event(event_text)
        
        assert event['data'] == '{"message": "hello"}'
        assert event.get('id') is None
    
    def test_parse_sse_event_multiline_data(self):
        """Test parsing SSE event with multiline data."""
        from praisonaiagents.mcp.mcp_session import parse_sse_event
        
        event_text = "data: line1\ndata: line2\n\n"
        event = parse_sse_event(event_text)
        
        assert event['data'] == 'line1\nline2'
    
    def test_parse_sse_event_empty_data(self):
        """Test parsing SSE event with empty data (for priming)."""
        from praisonaiagents.mcp.mcp_session import parse_sse_event
        
        event_text = "id: prime-123\ndata: \n\n"
        event = parse_sse_event(event_text)
        
        assert event['id'] == 'prime-123'
        assert event['data'] == ''


class TestEventStore:
    """Test optional event store for message redelivery."""
    
    def test_event_store_creation(self):
        """Test EventStore can be created."""
        from praisonaiagents.mcp.mcp_session import EventStore
        
        store = EventStore(max_events=100)
        assert store.max_events == 100
    
    def test_store_and_retrieve_event(self):
        """Test storing and retrieving events."""
        from praisonaiagents.mcp.mcp_session import EventStore
        
        store = EventStore()
        
        store.store("stream-1", "event-1", {"data": "test1"})
        store.store("stream-1", "event-2", {"data": "test2"})
        
        events = store.get_events_after("stream-1", "event-1")
        
        assert len(events) == 1
        assert events[0] == {"data": "test2"}
    
    def test_store_respects_max_events(self):
        """Test that store respects max_events limit."""
        from praisonaiagents.mcp.mcp_session import EventStore
        
        store = EventStore(max_events=3)
        
        for i in range(5):
            store.store("stream-1", f"event-{i}", {"data": i})
        
        # Should only have last 3 events
        all_events = store.get_all_events("stream-1")
        assert len(all_events) <= 3
    
    def test_store_per_stream_isolation(self):
        """Test that events are isolated per stream."""
        from praisonaiagents.mcp.mcp_session import EventStore
        
        store = EventStore()
        
        store.store("stream-1", "event-a", {"data": "a"})
        store.store("stream-2", "event-b", {"data": "b"})
        
        events_1 = store.get_all_events("stream-1")
        events_2 = store.get_all_events("stream-2")
        
        assert len(events_1) == 1
        assert len(events_2) == 1
        assert events_1[0] == {"data": "a"}
        assert events_2[0] == {"data": "b"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
