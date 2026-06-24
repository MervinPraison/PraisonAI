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


class TestConnectErrorEnvelope:
    """Tests for the structured connect-rejection envelope (Issue #2227)."""

    def test_new_error_codes_exist(self):
        """Transport-level rejections now have machine-readable codes."""
        from praisonaiagents.gateway.protocols import ConnectErrorCode

        assert ConnectErrorCode.RATE_LIMITED.value == "rate_limited"
        assert ConnectErrorCode.ORIGIN_NOT_ALLOWED.value == "origin_not_allowed"
        assert ConnectErrorCode.CONFIGURATION_ERROR.value == "configuration_error"

    def test_recovery_step_enum(self):
        """ConnectRecoveryStep exposes the deterministic recovery vocabulary."""
        from praisonaiagents.gateway.protocols import ConnectRecoveryStep

        assert ConnectRecoveryStep.REAUTHENTICATE.value == "reauthenticate"
        assert ConnectRecoveryStep.REPAIR.value == "repair"
        assert ConnectRecoveryStep.UPGRADE_CLIENT.value == "upgrade_client"
        assert ConnectRecoveryStep.DOWNGRADE_CLIENT.value == "downgrade_client"
        assert ConnectRecoveryStep.WAIT_THEN_RETRY.value == "wait_then_retry"
        assert ConnectRecoveryStep.DO_NOT_RETRY.value == "do_not_retry"

    def test_to_dict_with_recovery_fields(self):
        """Envelope carries code, next_step and retry_after for backoff."""
        from praisonaiagents.gateway.protocols import (
            ConnectErrorCode,
            ConnectRecoveryStep,
            HelloError,
        )

        frame = HelloError(
            code=ConnectErrorCode.RATE_LIMITED,
            message="Too many attempts",
            next_step=ConnectRecoveryStep.WAIT_THEN_RETRY,
            retry_after_seconds=30,
        ).to_dict()

        assert frame["type"] == "hello_error"
        assert frame["code"] == "rate_limited"
        assert frame["message"] == "Too many attempts"
        assert frame["next_step"] == "wait_then_retry"
        assert frame["retry_after_seconds"] == 30

    def test_to_dict_backward_compatible_next_field(self):
        """Legacy 'next' key is preserved for existing clients."""
        from praisonaiagents.gateway.protocols import (
            ConnectErrorCode,
            HelloError,
        )

        frame = HelloError(
            code=ConnectErrorCode.AGENT_NOT_FOUND,
            message="nope",
            next_action="check_agent_id",
        ).to_dict()

        assert frame["next"] == "check_agent_id"
        assert "next_step" not in frame
        assert "retry_after_seconds" not in frame

    def test_to_dict_next_falls_back_to_next_step(self):
        """When only next_step is set, legacy 'next' mirrors its value."""
        from praisonaiagents.gateway.protocols import (
            ConnectErrorCode,
            ConnectRecoveryStep,
            HelloError,
        )

        frame = HelloError(
            code=ConnectErrorCode.PROTOCOL_UNSUPPORTED,
            message="old",
            next_step=ConnectRecoveryStep.UPGRADE_CLIENT,
        ).to_dict()

        assert frame["next_step"] == "upgrade_client"
        assert frame["next"] == "upgrade_client"

    def test_to_dict_omits_next_when_no_hint(self):
        """Legacy 'next' key is omitted (not null) when no recovery hint set."""
        from praisonaiagents.gateway.protocols import ConnectErrorCode, HelloError

        frame = HelloError(
            code=ConnectErrorCode.CONFIGURATION_ERROR,
            message="bad config",
        ).to_dict()

        assert "next" not in frame
        assert "next_step" not in frame
        assert "retry_after_seconds" not in frame

    def test_downgrade_client_for_protocol_too_new(self):
        """A client newer than the server is told to downgrade, not upgrade."""
        from praisonaiagents.gateway.protocols import (
            ConnectErrorCode,
            ConnectRecoveryStep,
            HelloError,
        )

        frame = HelloError(
            code=ConnectErrorCode.PROTOCOL_UNSUPPORTED,
            message="Protocol version 2 is too new, server supports up to 1",
            next_step=ConnectRecoveryStep.DOWNGRADE_CLIENT,
            next_action="use_older_client",
        ).to_dict()

        assert frame["next_step"] == "downgrade_client"
        assert frame["next"] == "use_older_client"
