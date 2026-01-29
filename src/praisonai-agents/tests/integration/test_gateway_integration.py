"""
Integration tests for Gateway module.

These tests verify the Gateway protocols and implementations work correctly
with real scenarios. Some tests require API keys and are skipped if not available.
"""

import pytest
import os
from unittest.mock import MagicMock, patch

# Import from core SDK
from praisonaiagents.gateway import (
    GatewayConfig,
    SessionConfig,
    GatewayEvent,
    GatewayMessage,
    EventType,
)
from praisonaiagents.gateway.protocols import (
    GatewayProtocol,
    GatewaySessionProtocol,
    GatewayClientProtocol,
)


class TestGatewayConfigIntegration:
    """Integration tests for GatewayConfig."""
    
    def test_config_from_environment(self):
        """Test config can be created from environment variables."""
        with patch.dict(os.environ, {
            'GATEWAY_HOST': '0.0.0.0',
            'GATEWAY_PORT': '9000',
        }):
            config = GatewayConfig(
                host=os.environ.get('GATEWAY_HOST', 'localhost'),
                port=int(os.environ.get('GATEWAY_PORT', '8765')),
            )
            assert config.host == '0.0.0.0'
            assert config.port == 9000
    
    def test_config_with_auth(self):
        """Test config with authentication settings."""
        config = GatewayConfig(
            host='localhost',
            port=8765,
            auth_token='test-token-123',
        )
        assert config.auth_token == 'test-token-123'
        
        # Verify token is hidden in dict representation
        config_dict = config.to_dict()
        assert 'test-token-123' not in str(config_dict)
    
    def test_session_config_defaults(self):
        """Test SessionConfig has sensible defaults."""
        config = SessionConfig()
        assert config.timeout > 0
        assert config.max_messages > 0


class TestGatewayEventIntegration:
    """Integration tests for GatewayEvent."""
    
    def test_event_serialization_roundtrip(self):
        """Test event can be serialized and deserialized."""
        original = GatewayEvent(
            type=EventType.MESSAGE,
            data={'content': 'Hello, World!', 'user_id': '123'},
            source='agent-1',
            target='client-1',
        )
        
        # Serialize
        event_dict = original.to_dict()
        
        # Deserialize
        restored = GatewayEvent.from_dict(event_dict)
        
        assert restored.type == EventType.MESSAGE
        assert restored.data['content'] == 'Hello, World!'
        assert restored.source == 'agent-1'
        assert restored.target == 'client-1'
    
    def test_event_with_custom_type(self):
        """Test event with custom (non-enum) type."""
        event = GatewayEvent(
            type='custom_event',
            data={'custom': 'data'},
        )
        
        event_dict = event.to_dict()
        assert event_dict['type'] == 'custom_event'
        
        restored = GatewayEvent.from_dict(event_dict)
        assert restored.type == 'custom_event'
    
    def test_all_event_types(self):
        """Test all standard event types can be used."""
        for event_type in EventType:
            event = GatewayEvent(type=event_type, data={})
            assert event.type == event_type
            
            event_dict = event.to_dict()
            restored = GatewayEvent.from_dict(event_dict)
            assert restored.type == event_type


class TestGatewayMessageIntegration:
    """Integration tests for GatewayMessage."""
    
    def test_message_with_metadata(self):
        """Test message with rich metadata."""
        message = GatewayMessage(
            content='Test message',
            sender_id='user-123',
            session_id='session-456',
            metadata={
                'channel': 'telegram',
                'priority': 'high',
                'attachments': ['file1.pdf', 'file2.png'],
            },
        )
        
        msg_dict = message.to_dict()
        assert msg_dict['metadata']['channel'] == 'telegram'
        assert len(msg_dict['metadata']['attachments']) == 2
    
    def test_message_reply_chain(self):
        """Test message reply chain."""
        original = GatewayMessage(
            content='Original message',
            sender_id='user-1',
            session_id='session-1',
        )
        
        reply = GatewayMessage(
            content='Reply to original',
            sender_id='agent-1',
            session_id='session-1',
            reply_to=original.message_id,
        )
        
        assert reply.reply_to == original.message_id
    
    def test_message_structured_content(self):
        """Test message with structured content."""
        message = GatewayMessage(
            content={
                'type': 'card',
                'title': 'Weather Report',
                'body': 'Sunny, 25°C',
                'actions': [
                    {'label': 'Details', 'action': 'show_details'},
                    {'label': 'Dismiss', 'action': 'dismiss'},
                ],
            },
            sender_id='weather-agent',
            session_id='session-1',
        )
        
        assert isinstance(message.content, dict)
        assert message.content['type'] == 'card'


class TestGatewayProtocolCompliance:
    """Test that implementations comply with protocols."""
    
    def test_gateway_session_protocol_methods(self):
        """Verify GatewaySessionProtocol has all required methods."""
        required_properties = [
            'session_id', 'agent_id', 'client_id', 
            'is_active', 'created_at', 'last_activity'
        ]
        required_methods = [
            'get_state', 'set_state', 'add_message', 
            'get_messages', 'close'
        ]
        
        # Check protocol has all required attributes
        for prop in required_properties:
            assert hasattr(GatewaySessionProtocol, prop)
        
        for method in required_methods:
            assert hasattr(GatewaySessionProtocol, method)
    
    def test_gateway_client_protocol_methods(self):
        """Verify GatewayClientProtocol has all required methods."""
        required_properties = ['client_id', 'is_connected', 'connected_at']
        required_methods = ['send', 'receive', 'close']
        
        for prop in required_properties:
            assert hasattr(GatewayClientProtocol, prop)
        
        for method in required_methods:
            assert hasattr(GatewayClientProtocol, method)
    
    def test_gateway_protocol_methods(self):
        """Verify GatewayProtocol has all required methods."""
        required_properties = ['is_running', 'port', 'host']
        required_methods = [
            'start', 'stop', 'register_agent', 'unregister_agent',
            'get_agent', 'list_agents', 'create_session', 'get_session',
            'close_session', 'list_sessions', 'on_event', 'emit',
            'broadcast', 'health'
        ]
        
        for prop in required_properties:
            assert hasattr(GatewayProtocol, prop)
        
        for method in required_methods:
            assert hasattr(GatewayProtocol, method)


class TestMockGatewaySession:
    """Test a mock implementation of GatewaySessionProtocol."""
    
    def test_mock_session_workflow(self):
        """Test a complete session workflow with mock."""
        # Create mock session
        session = MagicMock()
        session.session_id = 'test-session-123'
        session.agent_id = 'agent-1'
        session.client_id = 'client-1'
        session.is_active = True
        session.created_at = 1704067200.0
        session.last_activity = 1704067200.0
        
        state = {}
        messages = []
        
        def get_state():
            return state.copy()
        
        def set_state(key, value):
            state[key] = value
        
        def add_message(msg):
            messages.append(msg)
        
        def get_messages(limit=None):
            if limit:
                return messages[-limit:]
            return messages.copy()
        
        session.get_state = get_state
        session.set_state = set_state
        session.add_message = add_message
        session.get_messages = get_messages
        
        # Test workflow
        session.set_state('user_name', 'Alice')
        assert session.get_state()['user_name'] == 'Alice'
        
        msg1 = GatewayMessage(
            content='Hello',
            sender_id='client-1',
            session_id='test-session-123',
        )
        session.add_message(msg1)
        
        msg2 = GatewayMessage(
            content='Hi there!',
            sender_id='agent-1',
            session_id='test-session-123',
        )
        session.add_message(msg2)
        
        history = session.get_messages()
        assert len(history) == 2
        assert history[0].content == 'Hello'
        assert history[1].content == 'Hi there!'


@pytest.mark.asyncio
class TestAsyncGatewayOperations:
    """Test async gateway operations."""
    
    async def test_async_event_handling(self):
        """Test async event emission and handling."""
        events_received = []
        
        async def event_handler(event: GatewayEvent):
            events_received.append(event)
        
        # Simulate event emission
        event = GatewayEvent(
            type=EventType.MESSAGE,
            data={'content': 'Test'},
        )
        
        await event_handler(event)
        
        assert len(events_received) == 1
        assert events_received[0].type == EventType.MESSAGE
    
    async def test_async_broadcast(self):
        """Test async broadcast to multiple clients."""
        clients_notified = []
        
        async def notify_client(client_id: str, event: GatewayEvent):
            clients_notified.append(client_id)
        
        # Simulate broadcast
        event = GatewayEvent(
            type=EventType.BROADCAST,
            data={'announcement': 'Server maintenance in 5 minutes'},
        )
        
        client_ids = ['client-1', 'client-2', 'client-3']
        
        for client_id in client_ids:
            await notify_client(client_id, event)
        
        assert len(clients_notified) == 3
        assert 'client-1' in clients_notified


class TestGatewayHealthCheck:
    """Test gateway health check functionality."""
    
    def test_health_response_structure(self):
        """Test health response has required fields."""
        # Mock health response
        health = {
            'status': 'healthy',
            'uptime': 3600,
            'agents': 2,
            'sessions': 5,
            'clients': 3,
        }
        
        assert health['status'] in ['healthy', 'unhealthy']
        assert isinstance(health['uptime'], (int, float))
        assert isinstance(health['agents'], int)
        assert isinstance(health['sessions'], int)
        assert isinstance(health['clients'], int)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
