"""
Tests for MCP HTTP Stream Transport features.

Tests the HTTPStreamTransport implementation including:
- Protocol version header (Mcp-Protocol-Version)
- Session management (Mcp-Session-Id)
- Resumability (Last-Event-ID, retry delay)
- Session termination (HTTP DELETE)
- SSE event parsing
"""

import pytest


class TestHTTPStreamTransportInit:
    """Test HTTPStreamTransport initialization."""
    
    def test_transport_has_protocol_version_header(self):
        """Test that transport includes Mcp-Protocol-Version header."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport('https://api.example.com/mcp')
        
        assert 'Mcp-Protocol-Version' in transport.headers
        assert transport.headers['Mcp-Protocol-Version'] == '2025-03-26'
    
    def test_transport_default_protocol_version(self):
        """Test default protocol version for backward compatibility."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        assert HTTPStreamTransport.DEFAULT_PROTOCOL_VERSION == '2025-03-26'
    
    def test_transport_custom_protocol_version(self):
        """Test custom protocol version via options."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport(
            'https://api.example.com/mcp',
            options={'protocol_version': '2025-11-25'}
        )
        
        assert transport.headers['Mcp-Protocol-Version'] == '2025-11-25'
    
    def test_transport_has_accept_header(self):
        """Test that transport includes correct Accept header."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport('https://api.example.com/mcp')
        
        assert 'Accept' in transport.headers
        assert 'application/json' in transport.headers['Accept']
        assert 'text/event-stream' in transport.headers['Accept']
    
    def test_transport_has_session_id_when_provided(self):
        """Test that transport includes session ID when provided."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport(
            'https://api.example.com/mcp',
            session_id='test-session-123'
        )
        
        assert 'Mcp-Session-Id' in transport.headers
        assert transport.headers['Mcp-Session-Id'] == 'test-session-123'
    
    def test_transport_no_session_id_when_not_provided(self):
        """Test that transport doesn't include session ID when not provided."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport('https://api.example.com/mcp')
        
        assert 'Mcp-Session-Id' not in transport.headers


class TestHTTPStreamTransportResumability:
    """Test HTTPStreamTransport resumability features."""
    
    def test_transport_has_last_event_id_tracking(self):
        """Test that transport tracks last event ID."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport('https://api.example.com/mcp')
        
        assert hasattr(transport, 'last_event_id')
        assert transport.last_event_id is None
    
    def test_transport_has_retry_delay_tracking(self):
        """Test that transport tracks retry delay."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport('https://api.example.com/mcp')
        
        assert hasattr(transport, '_retry_delay_ms')
        assert transport._retry_delay_ms == 3000  # Default 3 seconds
    
    def test_transport_updates_last_event_id(self):
        """Test that last_event_id can be updated."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport('https://api.example.com/mcp')
        transport.last_event_id = 'event-123'
        
        assert transport.last_event_id == 'event-123'
    
    def test_transport_updates_retry_delay(self):
        """Test that retry delay can be updated."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport('https://api.example.com/mcp')
        transport._retry_delay_ms = 5000
        
        assert transport._retry_delay_ms == 5000


class TestHTTPStreamTransportSessionTermination:
    """Test HTTPStreamTransport session termination."""
    
    def test_transport_has_terminate_session_method(self):
        """Test that transport has terminate_session method."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport('https://api.example.com/mcp')
        
        assert hasattr(transport, 'terminate_session')
        assert callable(transport.terminate_session)
    
    @pytest.mark.asyncio
    async def test_terminate_session_returns_false_without_session(self):
        """Test that terminate_session returns False without session."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport('https://api.example.com/mcp')
        
        # No session, should return False
        result = await transport.terminate_session()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_terminate_session_returns_false_without_client_session(self):
        """Test that terminate_session returns False without aiohttp session."""
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport(
            'https://api.example.com/mcp',
            session_id='test-session'
        )
        # _session is None (not initialized)
        
        result = await transport.terminate_session()
        assert result is False


class TestHTTPStreamTransportAutoDetection:
    """Test transport auto-detection in MCP class."""
    
    def test_http_url_uses_http_stream_transport(self):
        """Test that HTTP URLs use HTTPStreamTransport."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type('http://localhost:8080/mcp') == 'http_stream'
        assert get_transport_type('https://api.example.com/mcp') == 'http_stream'
    
    def test_sse_url_uses_sse_transport(self):
        """Test that SSE URLs use SSE transport."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type('http://localhost:8080/sse') == 'sse'
        assert get_transport_type('https://api.example.com/sse') == 'sse'
    
    def test_websocket_url_uses_websocket_transport(self):
        """Test that WebSocket URLs use WebSocket transport."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type('ws://localhost:8080/mcp') == 'websocket'
        assert get_transport_type('wss://api.example.com/mcp') == 'websocket'
    
    def test_command_string_uses_stdio_transport(self):
        """Test that command strings use stdio transport."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type('npx @modelcontextprotocol/server-memory') == 'stdio'
        assert get_transport_type('python3 server.py') == 'stdio'


class TestSSEEventParsing:
    """Test SSE event parsing for resumability."""
    
    def test_parse_sse_event_with_id(self):
        """Test parsing SSE event with id field."""
        from praisonaiagents.mcp.mcp_session import parse_sse_event
        
        event_text = "id: event-123\ndata: {\"test\": true}"
        result = parse_sse_event(event_text)
        
        assert result['id'] == 'event-123'
        assert result['data'] == '{"test": true}'
    
    def test_parse_sse_event_with_retry(self):
        """Test parsing SSE event with retry field."""
        from praisonaiagents.mcp.mcp_session import parse_sse_event
        
        event_text = "retry: 5000\ndata: {\"test\": true}"
        result = parse_sse_event(event_text)
        
        assert result['retry'] == 5000
        assert result['data'] == '{"test": true}'
    
    def test_parse_sse_event_with_all_fields(self):
        """Test parsing SSE event with all fields."""
        from praisonaiagents.mcp.mcp_session import parse_sse_event
        
        event_text = "id: event-456\nretry: 3000\ndata: {\"jsonrpc\": \"2.0\"}"
        result = parse_sse_event(event_text)
        
        assert result['id'] == 'event-456'
        assert result['retry'] == 3000
        assert result['data'] == '{"jsonrpc": "2.0"}'
    
    def test_parse_sse_event_multiline_data(self):
        """Test parsing SSE event with multiline data."""
        from praisonaiagents.mcp.mcp_session import parse_sse_event
        
        event_text = "data: line1\ndata: line2"
        result = parse_sse_event(event_text)
        
        assert result['data'] == 'line1\nline2'


class TestResumabilityManager:
    """Test ResumabilityManager for SSE stream recovery."""
    
    def test_manager_tracks_event_ids(self):
        """Test that manager tracks event IDs per stream."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        manager.set_last_event_id('stream1', 'event-100')
        manager.set_last_event_id('stream2', 'event-200')
        
        assert manager.get_last_event_id('stream1') == 'event-100'
        assert manager.get_last_event_id('stream2') == 'event-200'
    
    def test_manager_returns_none_for_unknown_stream(self):
        """Test that manager returns None for unknown stream."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        
        assert manager.get_last_event_id('unknown') is None
    
    def test_manager_generates_resume_headers(self):
        """Test that manager generates Last-Event-ID header."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        manager.set_last_event_id('stream1', 'event-123')
        
        headers = manager.get_resume_headers('stream1')
        
        assert 'Last-Event-ID' in headers
        assert headers['Last-Event-ID'] == 'event-123'
    
    def test_manager_tracks_retry_delay(self):
        """Test that manager tracks retry delay."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        manager.set_retry_delay(5000)
        
        assert manager.get_retry_delay() == 5000
    
    def test_manager_default_retry_delay(self):
        """Test default retry delay."""
        from praisonaiagents.mcp.mcp_session import ResumabilityManager
        
        manager = ResumabilityManager()
        
        # Default should be 3000ms
        assert manager.get_retry_delay() == 3000


class TestEventStore:
    """Test EventStore for message replay."""
    
    def test_store_events(self):
        """Test storing events."""
        from praisonaiagents.mcp.mcp_session import EventStore
        
        store = EventStore(max_events=100)
        store.store('stream1', 'event-1', {'data': 'test1'})
        store.store('stream1', 'event-2', {'data': 'test2'})
        
        events = store.get_all_events('stream1')
        assert len(events) == 2
    
    def test_get_events_after_id(self):
        """Test getting events after specific ID."""
        from praisonaiagents.mcp.mcp_session import EventStore
        
        store = EventStore(max_events=100)
        store.store('stream1', 'event-1', {'data': 'test1'})
        store.store('stream1', 'event-2', {'data': 'test2'})
        store.store('stream1', 'event-3', {'data': 'test3'})
        
        events = store.get_events_after('stream1', 'event-1')
        assert len(events) == 2
        assert events[0]['data'] == 'test2'
        assert events[1]['data'] == 'test3'
    
    def test_store_respects_max_events(self):
        """Test that store respects max_events limit."""
        from praisonaiagents.mcp.mcp_session import EventStore
        
        store = EventStore(max_events=3)
        for i in range(5):
            store.store('stream1', f'event-{i}', {'data': f'test{i}'})
        
        events = store.get_all_events('stream1')
        assert len(events) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
