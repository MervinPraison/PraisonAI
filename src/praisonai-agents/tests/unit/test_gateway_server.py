"""
Tests for WebSocket Gateway Server.

TDD: Mock-based tests for WebSocketGateway — no actual server started.
Tests existing functionality and multi-bot extensions (Agent 2).
"""

from unittest.mock import Mock

from praisonaiagents.gateway import (
    GatewayConfig,
    GatewayEvent,
    GatewayMessage,
    EventType,
)


class TestGatewayImports:
    """Test that gateway modules import correctly."""

    def test_import_gateway_config(self):
        """Test GatewayConfig import."""
        assert GatewayConfig is not None

    def test_import_gateway_event(self):
        """Test GatewayEvent import."""
        assert GatewayEvent is not None

    def test_import_event_type(self):
        """Test EventType import."""
        assert EventType is not None

    def test_import_gateway_message(self):
        """Test GatewayMessage import."""
        assert GatewayMessage is not None


class TestGatewayEvent:
    """Tests for GatewayEvent dataclass."""

    def test_event_creation(self):
        """Test basic event creation."""
        event = GatewayEvent(type=EventType.MESSAGE, data={"text": "hello"})
        assert event.type == EventType.MESSAGE
        assert event.data == {"text": "hello"}
        assert event.event_id is not None
        assert event.timestamp > 0

    def test_event_with_source_target(self):
        """Test event with source and target."""
        event = GatewayEvent(
            type=EventType.MESSAGE,
            data={},
            source="client_1",
            target="agent_1",
        )
        assert event.source == "client_1"
        assert event.target == "agent_1"

    def test_event_to_dict(self):
        """Test event serialization."""
        event = GatewayEvent(
            type=EventType.CONNECT,
            data={"client_id": "abc"},
            source="client",
        )
        d = event.to_dict()
        assert d["type"] == "connect"
        assert d["data"] == {"client_id": "abc"}
        assert d["source"] == "client"
        assert "event_id" in d
        assert "timestamp" in d

    def test_event_from_dict(self):
        """Test event deserialization."""
        d = {
            "type": "message",
            "data": {"text": "hello"},
            "event_id": "test-id",
            "timestamp": 1234567890.0,
            "source": "client",
            "target": "agent",
        }
        event = GatewayEvent.from_dict(d)
        assert event.type == EventType.MESSAGE
        assert event.data == {"text": "hello"}
        assert event.event_id == "test-id"
        assert event.source == "client"
        assert event.target == "agent"

    def test_event_from_dict_custom_type(self):
        """Test event deserialization with custom type string."""
        d = {"type": "custom.event", "data": {}}
        event = GatewayEvent.from_dict(d)
        assert event.type == "custom.event"

    def test_event_string_type(self):
        """Test event with string type instead of enum."""
        event = GatewayEvent(type="custom.type", data={})
        assert event.type == "custom.type"
        d = event.to_dict()
        assert d["type"] == "custom.type"


class TestGatewayMessage:
    """Tests for GatewayMessage dataclass."""

    def test_message_creation(self):
        """Test basic message creation."""
        msg = GatewayMessage(
            content="Hello",
            sender_id="user_1",
            session_id="session_1",
        )
        assert msg.content == "Hello"
        assert msg.sender_id == "user_1"
        assert msg.session_id == "session_1"
        assert msg.message_id is not None
        assert msg.timestamp > 0

    def test_message_to_dict(self):
        """Test message serialization."""
        msg = GatewayMessage(
            content="Test",
            sender_id="user",
            session_id="sess",
        )
        d = msg.to_dict()
        assert d["content"] == "Test"
        assert d["sender_id"] == "user"
        assert d["session_id"] == "sess"
        assert "message_id" in d

    def test_message_from_dict(self):
        """Test message deserialization."""
        d = {
            "content": "Hello",
            "sender_id": "user",
            "session_id": "sess",
            "message_id": "msg-1",
            "timestamp": 1000.0,
            "reply_to": "msg-0",
        }
        msg = GatewayMessage.from_dict(d)
        assert msg.content == "Hello"
        assert msg.sender_id == "user"
        assert msg.session_id == "sess"
        assert msg.message_id == "msg-1"
        assert msg.reply_to == "msg-0"

    def test_message_from_dict_defaults(self):
        """Test message deserialization with minimal data."""
        d = {}
        msg = GatewayMessage.from_dict(d)
        assert msg.content == ""
        assert msg.sender_id == "unknown"
        assert msg.session_id == "default"


class TestEventType:
    """Tests for EventType enum."""

    def test_connection_events(self):
        """Test connection event types exist."""
        assert EventType.CONNECT.value == "connect"
        assert EventType.DISCONNECT.value == "disconnect"
        assert EventType.RECONNECT.value == "reconnect"

    def test_session_events(self):
        """Test session event types exist."""
        assert EventType.SESSION_START.value == "session_start"
        assert EventType.SESSION_END.value == "session_end"
        assert EventType.SESSION_UPDATE.value == "session_update"

    def test_agent_events(self):
        """Test agent event types exist."""
        assert EventType.AGENT_REGISTER.value == "agent_register"
        assert EventType.AGENT_UNREGISTER.value == "agent_unregister"
        assert EventType.AGENT_STATUS.value == "agent_status"

    def test_message_events(self):
        """Test message event types exist."""
        assert EventType.MESSAGE.value == "message"
        assert EventType.MESSAGE_ACK.value == "message_ack"
        assert EventType.TYPING.value == "typing"

    def test_system_events(self):
        """Test system event types exist."""
        assert EventType.HEALTH.value == "health"
        assert EventType.ERROR.value == "error"
        assert EventType.BROADCAST.value == "broadcast"


class TestWebSocketGateway:
    """Tests for WebSocketGateway server (wrapper package)."""

    def _get_gateway_class(self):
        """Import WebSocketGateway with graceful fallback."""
        try:
            from praisonai.gateway import WebSocketGateway
            return WebSocketGateway
        except ImportError:
            return None

    def test_import(self):
        """Test WebSocketGateway can be imported."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        assert cls is not None

    def test_instantiation_defaults(self):
        """Test WebSocketGateway default instantiation."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        assert gw.host == "127.0.0.1"
        assert gw.port == 8765
        assert gw.is_running is False

    def test_instantiation_custom(self):
        """Test WebSocketGateway with custom config."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        config = GatewayConfig(host="0.0.0.0", port=9000)
        gw = cls(config=config)
        assert gw.host == "0.0.0.0"
        assert gw.port == 9000

    def test_register_agent(self):
        """Test agent registration."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        mock_agent = Mock()
        mock_agent.agent_id = None
        agent_id = gw.register_agent(mock_agent, agent_id="test-agent")
        assert agent_id == "test-agent"
        assert "test-agent" in gw.list_agents()

    def test_register_agent_auto_id(self):
        """Test agent registration with auto-generated ID."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        mock_agent = Mock()
        mock_agent.agent_id = None
        agent_id = gw.register_agent(mock_agent)
        assert agent_id is not None
        assert len(agent_id) > 0

    def test_unregister_agent(self):
        """Test agent unregistration."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        mock_agent = Mock()
        mock_agent.agent_id = None
        gw.register_agent(mock_agent, agent_id="to-remove")
        result = gw.unregister_agent("to-remove")
        assert result is True
        assert "to-remove" not in gw.list_agents()

    def test_unregister_agent_not_found(self):
        """Test unregistering non-existent agent."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        result = gw.unregister_agent("nonexistent")
        assert result is False

    def test_get_agent(self):
        """Test getting a registered agent."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        mock_agent = Mock()
        mock_agent.agent_id = None
        gw.register_agent(mock_agent, agent_id="my-agent")
        retrieved = gw.get_agent("my-agent")
        assert retrieved is mock_agent

    def test_get_agent_not_found(self):
        """Test getting non-existent agent."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        assert gw.get_agent("nonexistent") is None

    def test_list_agents_empty(self):
        """Test listing agents when none registered."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        assert gw.list_agents() == []

    def test_list_agents_multiple(self):
        """Test listing multiple agents."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        for name in ["agent_a", "agent_b", "agent_c"]:
            mock = Mock()
            mock.agent_id = None
            gw.register_agent(mock, agent_id=name)
        agents = gw.list_agents()
        assert len(agents) == 3
        assert "agent_a" in agents
        assert "agent_b" in agents
        assert "agent_c" in agents

    def test_create_session(self):
        """Test session creation."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        mock_agent = Mock()
        mock_agent.agent_id = None
        gw.register_agent(mock_agent, agent_id="agent_1")
        session = gw.create_session("agent_1", client_id="client_1")
        assert session.session_id is not None
        assert session.agent_id == "agent_1"
        assert session.client_id == "client_1"
        assert session.is_active is True

    def test_close_session(self):
        """Test session closing."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        mock_agent = Mock()
        mock_agent.agent_id = None
        gw.register_agent(mock_agent, agent_id="agent_1")
        session = gw.create_session("agent_1")
        result = gw.close_session(session.session_id)
        assert result is True

    def test_close_session_not_found(self):
        """Test closing non-existent session."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        result = gw.close_session("nonexistent")
        assert result is False

    def test_list_sessions(self):
        """Test listing sessions."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        mock_agent = Mock()
        mock_agent.agent_id = None
        gw.register_agent(mock_agent, agent_id="agent_1")
        gw.create_session("agent_1", session_id="sess_1")
        gw.create_session("agent_1", session_id="sess_2")
        sessions = gw.list_sessions()
        assert len(sessions) == 2
        assert "sess_1" in sessions
        assert "sess_2" in sessions

    def test_list_sessions_by_agent(self):
        """Test listing sessions filtered by agent."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        for aid in ["agent_a", "agent_b"]:
            mock = Mock()
            mock.agent_id = None
            gw.register_agent(mock, agent_id=aid)
        gw.create_session("agent_a", session_id="sess_a1")
        gw.create_session("agent_b", session_id="sess_b1")
        gw.create_session("agent_a", session_id="sess_a2")
        a_sessions = gw.list_sessions(agent_id="agent_a")
        assert len(a_sessions) == 2
        assert "sess_a1" in a_sessions
        assert "sess_a2" in a_sessions

    def test_health_stopped(self):
        """Test health status when gateway is stopped."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        health = gw.health()
        assert health["status"] == "stopped"
        assert health["agents"] == 0
        assert health["sessions"] == 0
        assert health["clients"] == 0

    def test_health_with_agents(self):
        """Test health status includes agent count."""
        cls = self._get_gateway_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        gw = cls()
        mock = Mock()
        mock.agent_id = None
        gw.register_agent(mock, agent_id="a1")
        health = gw.health()
        assert health["agents"] == 1


class TestGatewaySession:
    """Tests for GatewaySession (from wrapper)."""

    def _get_session_class(self):
        """Import GatewaySession with graceful fallback."""
        try:
            from praisonai.gateway import GatewaySession
            return GatewaySession
        except ImportError:
            return None

    def test_session_state(self):
        """Test session state management."""
        cls = self._get_session_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        session = cls(
            _session_id="test",
            _agent_id="agent_1",
        )
        session.set_state("key", "value")
        state = session.get_state()
        assert state["key"] == "value"

    def test_session_messages(self):
        """Test session message management."""
        cls = self._get_session_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        session = cls(
            _session_id="test",
            _agent_id="agent_1",
        )
        msg = GatewayMessage(content="Hello", sender_id="user", session_id="test")
        session.add_message(msg)
        messages = session.get_messages()
        assert len(messages) == 1
        assert messages[0].content == "Hello"

    def test_session_messages_limit(self):
        """Test session message retrieval with limit."""
        cls = self._get_session_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        session = cls(
            _session_id="test",
            _agent_id="agent_1",
        )
        for i in range(5):
            msg = GatewayMessage(content=f"msg_{i}", sender_id="user", session_id="test")
            session.add_message(msg)
        messages = session.get_messages(limit=2)
        assert len(messages) == 2

    def test_session_close(self):
        """Test session closing."""
        cls = self._get_session_class()
        if cls is None:
            __import__("pytest").skip("praisonai wrapper not installed")
        session = cls(
            _session_id="test",
            _agent_id="agent_1",
        )
        assert session.is_active is True
        session.close()
        assert session.is_active is False
