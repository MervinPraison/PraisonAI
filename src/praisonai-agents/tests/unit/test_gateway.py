"""
Unit tests for Gateway protocols and components.
"""

from praisonaiagents.gateway import (
    GatewayConfig,
    SessionConfig,
    GatewayEvent,
    GatewayMessage,
    EventType,
)


class TestGatewayConfig:
    """Tests for GatewayConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = GatewayConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8765
        assert config.max_connections == 1000
        assert config.heartbeat_interval == 30
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = GatewayConfig(
            host="0.0.0.0",
            port=9000,
            auth_token="secret",
        )
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert config.auth_token == "secret"
    
    def test_ws_url(self):
        """Test WebSocket URL generation."""
        config = GatewayConfig(host="localhost", port=8080)
        assert config.ws_url == "ws://localhost:8080"
    
    def test_secure_ws_url(self):
        """Test secure WebSocket URL generation."""
        config = GatewayConfig(
            host="localhost",
            port=443,
            ssl_cert="/path/to/cert",
            ssl_key="/path/to/key",
        )
        assert config.is_secure
        assert config.ws_url == "wss://localhost:443"
    
    def test_to_dict_hides_token(self):
        """Test that to_dict hides sensitive data."""
        config = GatewayConfig(auth_token="my-secret-token")
        data = config.to_dict()
        assert data["auth_token"] == "***"


class TestSessionConfig:
    """Tests for SessionConfig."""
    
    def test_default_session_config(self):
        """Test default session configuration."""
        config = SessionConfig()
        assert config.timeout == 3600
        assert config.max_messages == 1000
        assert config.persist is False
    
    def test_custom_session_config(self):
        """Test custom session configuration."""
        config = SessionConfig(
            timeout=7200,
            max_messages=500,
            persist=True,
            persist_path="/tmp/sessions",
        )
        assert config.timeout == 7200
        assert config.max_messages == 500
        assert config.persist is True


class TestGatewayEvent:
    """Tests for GatewayEvent."""
    
    def test_event_creation(self):
        """Test event creation."""
        event = GatewayEvent(
            type=EventType.MESSAGE,
            data={"content": "Hello"},
            source="client-1",
        )
        assert event.type == EventType.MESSAGE
        assert event.data["content"] == "Hello"
        assert event.source == "client-1"
        assert event.event_id is not None
        assert event.timestamp > 0
    
    def test_event_to_dict(self):
        """Test event serialization."""
        event = GatewayEvent(
            type=EventType.CONNECT,
            data={"client_id": "123"},
        )
        data = event.to_dict()
        assert data["type"] == "connect"
        assert data["data"]["client_id"] == "123"
    
    def test_event_from_dict(self):
        """Test event deserialization."""
        data = {
            "type": "message",
            "data": {"text": "Hello"},
            "source": "user-1",
        }
        event = GatewayEvent.from_dict(data)
        assert event.type == EventType.MESSAGE
        assert event.data["text"] == "Hello"
        assert event.source == "user-1"
    
    def test_custom_event_type(self):
        """Test custom event type handling."""
        event = GatewayEvent(type="custom_event", data={})
        assert event.type == "custom_event"
        
        data = event.to_dict()
        restored = GatewayEvent.from_dict(data)
        assert restored.type == "custom_event"


class TestGatewayMessage:
    """Tests for GatewayMessage."""
    
    def test_message_creation(self):
        """Test message creation."""
        msg = GatewayMessage(
            content="Hello, World!",
            sender_id="user-1",
            session_id="session-1",
        )
        assert msg.content == "Hello, World!"
        assert msg.sender_id == "user-1"
        assert msg.session_id == "session-1"
        assert msg.message_id is not None
    
    def test_message_to_dict(self):
        """Test message serialization."""
        msg = GatewayMessage(
            content="Test",
            sender_id="user",
            session_id="sess",
        )
        data = msg.to_dict()
        assert data["content"] == "Test"
        assert data["sender_id"] == "user"
        assert data["session_id"] == "sess"
    
    def test_message_from_dict(self):
        """Test message deserialization."""
        data = {
            "content": "Hello",
            "sender_id": "user-1",
            "session_id": "session-1",
            "reply_to": "msg-0",
        }
        msg = GatewayMessage.from_dict(data)
        assert msg.content == "Hello"
        assert msg.sender_id == "user-1"
        assert msg.reply_to == "msg-0"
    
    def test_message_with_metadata(self):
        """Test message with metadata."""
        msg = GatewayMessage(
            content="Test",
            sender_id="user",
            session_id="sess",
            metadata={"priority": "high"},
        )
        assert msg.metadata["priority"] == "high"


class TestEventType:
    """Tests for EventType enum."""
    
    def test_event_types(self):
        """Test event type values."""
        assert EventType.CONNECT.value == "connect"
        assert EventType.DISCONNECT.value == "disconnect"
        assert EventType.MESSAGE.value == "message"
        assert EventType.SESSION_START.value == "session_start"
        assert EventType.AGENT_REGISTER.value == "agent_register"
        assert EventType.HEALTH.value == "health"
