"""
TDD Tests for Gateway Integration Gaps (S1-S6).

Tests the fixes for PraisonAIUI gateway integration gaps.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch


class TestGapS6ClientManagement:
    """Test Gap S6: Public client management methods in WebSocketGateway."""

    def test_add_client(self):
        """add_client should register a client."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        mock_ws = Mock()
        
        gw.add_client("client-123", mock_ws)
        
        assert "client-123" in gw.list_clients()
        assert gw.get_client("client-123") == mock_ws

    def test_remove_client(self):
        """remove_client should unregister a client."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        mock_ws = Mock()
        gw.add_client("client-123", mock_ws)
        
        result = gw.remove_client("client-123")
        
        assert result is True
        assert "client-123" not in gw.list_clients()

    def test_remove_client_not_found(self):
        """remove_client should return False if client not found."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        result = gw.remove_client("nonexistent")
        
        assert result is False

    def test_get_client_not_found(self):
        """get_client should return None if client not found."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        result = gw.get_client("nonexistent")
        
        assert result is None

    def test_list_clients(self):
        """list_clients should return all client IDs."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        gw.add_client("client-1", Mock())
        gw.add_client("client-2", Mock())
        
        clients = gw.list_clients()
        
        assert len(clients) == 2
        assert "client-1" in clients
        assert "client-2" in clients


class TestGapS5ConfigFromFile:
    """Test Gap S5: Gateway config from YAML file."""

    def test_from_config_file_with_gateway_section(self):
        """from_config_file should load gateway settings from YAML."""
        from praisonai.gateway import WebSocketGateway
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("""
gateway:
  host: "0.0.0.0"
  port: 9000
  max_connections: 500
""")
            
            gw = WebSocketGateway.from_config_file(str(config_file))
            
            assert gw.host == "0.0.0.0"
            assert gw.port == 9000
            assert gw.config.max_connections == 500

    def test_from_config_file_missing_file(self):
        """from_config_file should use defaults if file not found."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway.from_config_file("/nonexistent/config.yaml")
        
        assert gw.host == "127.0.0.1"
        assert gw.port == 8765

    def test_from_config_file_no_gateway_section(self):
        """from_config_file should use defaults if no gateway section."""
        from praisonai.gateway import WebSocketGateway
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("""
other_section:
  key: value
""")
            
            gw = WebSocketGateway.from_config_file(str(config_file))
            
            assert gw.host == "127.0.0.1"
            assert gw.port == 8765


class TestGapS4AgentLevelQueries:
    """Test Gap S4: Agent-level memory/session queries."""

    def test_list_sessions_by_agent(self):
        """list_sessions_by_agent should return sessions for a specific agent."""
        from praisonaiagents.session import DefaultSessionStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            
            # Create sessions for different agents
            store.add_message("session-1", "user", "Hello")
            store.set_agent_info("session-1", agent_name="agent-a")
            
            store.add_message("session-2", "user", "Hi")
            store.set_agent_info("session-2", agent_name="agent-b")
            
            store.add_message("session-3", "user", "Hey")
            store.set_agent_info("session-3", agent_name="agent-a")
            
            # Query by agent
            sessions = store.list_sessions_by_agent("agent-a")
            
            assert len(sessions) == 2
            assert "session-1" in sessions
            assert "session-3" in sessions
            assert "session-2" not in sessions

    def test_get_sessions_by_agent(self):
        """get_sessions_by_agent should return full session data."""
        from praisonaiagents.session import DefaultSessionStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            
            store.add_message("session-1", "user", "Hello")
            store.set_agent_info("session-1", agent_name="agent-a")
            
            sessions = store.get_sessions_by_agent("agent-a")
            
            assert len(sessions) == 1
            assert sessions[0].session_id == "session-1"
            assert sessions[0].agent_name == "agent-a"

    def test_get_agent_chat_history(self):
        """get_agent_chat_history should return combined history."""
        from praisonaiagents.session import DefaultSessionStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            
            store.add_message("session-1", "user", "Hello")
            store.add_message("session-1", "assistant", "Hi there!")
            store.set_agent_info("session-1", agent_name="agent-a")
            
            history = store.get_agent_chat_history("agent-a")
            
            assert len(history) == 2
            assert history[0]["content"] == "Hello"
            assert history[0]["session_id"] == "session-1"
            assert history[0]["agent_name"] == "agent-a"


class TestGapS3GatewayAwareMemory:
    """Test Gap S3: Gateway-aware memory/session."""

    def test_session_data_has_gateway_fields(self):
        """SessionData should have gateway_session_id and agent_id fields."""
        from praisonaiagents.session import SessionData
        
        session = SessionData(
            session_id="test-session",
            gateway_session_id="gw-session-123",
            agent_id="gw-agent-456",
        )
        
        assert session.gateway_session_id == "gw-session-123"
        assert session.agent_id == "gw-agent-456"

    def test_session_data_serialization(self):
        """SessionData should serialize gateway fields."""
        from praisonaiagents.session import SessionData
        
        session = SessionData(
            session_id="test-session",
            gateway_session_id="gw-session-123",
            agent_id="gw-agent-456",
        )
        
        data = session.to_dict()
        
        assert data["gateway_session_id"] == "gw-session-123"
        assert data["agent_id"] == "gw-agent-456"

    def test_session_data_deserialization(self):
        """SessionData should deserialize gateway fields."""
        from praisonaiagents.session import SessionData
        
        data = {
            "session_id": "test-session",
            "gateway_session_id": "gw-session-123",
            "agent_id": "gw-agent-456",
        }
        
        session = SessionData.from_dict(data)
        
        assert session.gateway_session_id == "gw-session-123"
        assert session.agent_id == "gw-agent-456"

    def test_set_gateway_info(self):
        """set_gateway_info should link session to gateway."""
        from praisonaiagents.session import DefaultSessionStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            
            store.add_message("session-1", "user", "Hello")
            store.set_gateway_info(
                "session-1",
                gateway_session_id="gw-session-123",
                agent_id="gw-agent-456",
            )
            
            session = store.get_session("session-1")
            
            assert session.gateway_session_id == "gw-session-123"
            assert session.agent_id == "gw-agent-456"

    def test_get_by_gateway_session(self):
        """get_by_gateway_session should find session by gateway session ID."""
        from praisonaiagents.session import DefaultSessionStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            
            store.add_message("session-1", "user", "Hello")
            store.set_gateway_info("session-1", gateway_session_id="gw-session-123")
            
            session = store.get_by_gateway_session("gw-session-123")
            
            assert session is not None
            assert session.session_id == "session-1"

    def test_list_sessions_by_gateway_agent(self):
        """list_sessions_by_gateway_agent should find sessions by gateway agent ID."""
        from praisonaiagents.session import DefaultSessionStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            
            store.add_message("session-1", "user", "Hello")
            store.set_gateway_info("session-1", agent_id="gw-agent-456")
            
            store.add_message("session-2", "user", "Hi")
            store.set_gateway_info("session-2", agent_id="gw-agent-456")
            
            sessions = store.list_sessions_by_gateway_agent("gw-agent-456")
            
            assert len(sessions) == 2


class TestGapS2ReExportWebSocketGateway:
    """Test Gap S2: Re-export WebSocketGateway from praisonaiagents.gateway."""

    def test_import_websocketgateway_from_core(self):
        """WebSocketGateway should be importable from praisonaiagents.gateway."""
        from praisonaiagents.gateway import WebSocketGateway
        
        # Should not raise ImportError
        assert WebSocketGateway is not None

    def test_import_gatewaysession_from_core(self):
        """GatewaySession should be importable from praisonaiagents.gateway."""
        from praisonaiagents.gateway import GatewaySession
        
        # Should not raise ImportError
        assert GatewaySession is not None

    def test_protocols_always_available(self):
        """Protocols should always be available without praisonai wrapper."""
        from praisonaiagents.gateway import (
            GatewayProtocol,
            GatewaySessionProtocol,
            GatewayClientProtocol,
            GatewayEvent,
            GatewayMessage,
            EventType,
            GatewayConfig,
        )
        
        # All should be available
        assert GatewayProtocol is not None
        assert GatewaySessionProtocol is not None
        assert GatewayClientProtocol is not None
        assert GatewayEvent is not None
        assert GatewayMessage is not None
        assert EventType is not None
        assert GatewayConfig is not None
