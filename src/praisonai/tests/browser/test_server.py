"""Tests for browser server."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import json


class TestBrowserServerInit:
    """Tests for BrowserServer initialization."""
    
    def test_server_initialization(self):
        """Test server initializes with defaults."""
        from praisonai.browser.server import BrowserServer
        
        server = BrowserServer()
        
        assert server.host == "0.0.0.0"
        assert server.port == 8765
        assert server.model == "gpt-4o-mini"
        assert server.max_steps == 20
        assert server.verbose is False
    
    def test_server_custom_config(self):
        """Test server with custom configuration."""
        from praisonai.browser.server import BrowserServer
        
        server = BrowserServer(
            host="127.0.0.1",
            port=9999,
            model="gpt-4o",
            max_steps=10,
            verbose=True,
        )
        
        assert server.host == "127.0.0.1"
        assert server.port == 9999
        assert server.model == "gpt-4o"
        assert server.max_steps == 10
        assert server.verbose is True


class TestClientConnection:
    """Tests for ClientConnection dataclass."""
    
    def test_client_connection_creation(self):
        """Test creating a client connection."""
        from praisonai.browser.server import ClientConnection
        
        mock_ws = Mock()
        conn = ClientConnection(
            websocket=mock_ws,
            session_id="test123",
            connected_at=123456.789,
        )
        
        assert conn.websocket == mock_ws
        assert conn.session_id == "test123"
        assert conn.connected_at == 123456.789
    
    def test_client_connection_defaults(self):
        """Test client connection default values."""
        from praisonai.browser.server import ClientConnection
        
        mock_ws = Mock()
        conn = ClientConnection(websocket=mock_ws)
        
        assert conn.session_id is None
        assert conn.connected_at == 0.0


class TestServerAppCreation:
    """Tests for FastAPI app creation."""
    
    def test_get_app_creates_fastapi(self):
        """Test that _get_app creates FastAPI instance."""
        from praisonai.browser.server import BrowserServer
        
        server = BrowserServer()
        app = server._get_app()
        
        assert app is not None
        assert hasattr(app, "add_route")
    
    def test_get_app_singleton(self):
        """Test that _get_app returns same instance."""
        from praisonai.browser.server import BrowserServer
        
        server = BrowserServer()
        app1 = server._get_app()
        app2 = server._get_app()
        
        assert app1 is app2
    
    def test_health_endpoint_exists(self):
        """Test health endpoint is registered."""
        from praisonai.browser.server import BrowserServer
        
        server = BrowserServer()
        app = server._get_app()
        
        routes = [r.path for r in app.routes]
        assert "/health" in routes


class TestMessageProcessing:
    """Tests for message processing logic."""
    
    @pytest.mark.asyncio
    async def test_process_ping_message(self):
        """Test ping message returns pong."""
        from praisonai.browser.server import BrowserServer, ClientConnection
        
        server = BrowserServer()
        conn = ClientConnection(websocket=Mock())
        
        response = await server._process_message({"type": "ping"}, conn)
        
        assert response == {"type": "pong"}
    
    @pytest.mark.asyncio
    async def test_process_unknown_message(self):
        """Test unknown message type returns error."""
        from praisonai.browser.server import BrowserServer, ClientConnection
        
        server = BrowserServer()
        conn = ClientConnection(websocket=Mock())
        
        response = await server._process_message({"type": "unknown"}, conn)
        
        assert response["type"] == "error"
        assert "unknown" in response["error"].lower()
    
    @pytest.mark.asyncio
    async def test_process_start_session_missing_goal(self):
        """Test start session without goal returns error."""
        from praisonai.browser.server import BrowserServer, ClientConnection
        
        server = BrowserServer()
        conn = ClientConnection(websocket=Mock())
        
        response = await server._process_message(
            {"type": "start_session", "goal": ""},
            conn
        )
        
        assert response["type"] == "error"
        assert response["code"] == "MISSING_GOAL"
    
    @pytest.mark.asyncio
    async def test_process_stop_session(self):
        """Test stopping a session."""
        from praisonai.browser.server import BrowserServer, ClientConnection
        
        server = BrowserServer()
        conn = ClientConnection(websocket=Mock(), session_id="test123")
        
        response = await server._process_message(
            {"type": "stop_session"},
            conn
        )
        
        assert response["type"] == "status"
        assert response["status"] == "stopped"
    
    @pytest.mark.asyncio
    async def test_process_observation_no_session(self):
        """Test observation without active session returns error."""
        from praisonai.browser.server import BrowserServer, ClientConnection
        
        server = BrowserServer()
        conn = ClientConnection(websocket=Mock())
        
        response = await server._process_message(
            {"type": "observation", "task": "Test"},
            conn
        )
        
        assert response["type"] == "error"
        assert response["code"] == "NO_SESSION"


class TestServerStartStop:
    """Tests for server start/stop functionality."""
    
    def test_stop_clears_state(self):
        """Test that stop() clears connections and agents."""
        from praisonai.browser.server import BrowserServer
        
        server = BrowserServer()
        server._agents["test1"] = Mock()
        server._connections["conn1"] = Mock()
        
        server.stop()
        
        assert len(server._agents) == 0
        assert len(server._connections) == 0
        assert server._running is False


class TestStartSession:
    """Tests for session start handling."""
    
    @pytest.mark.asyncio
    async def test_handle_start_session_success(self):
        """Test successful session start."""
        from praisonai.browser.server import BrowserServer, ClientConnection
        
        server = BrowserServer()
        conn = ClientConnection(websocket=Mock())
        
        message = {
            "type": "start_session",
            "goal": "Find restaurants",
            "model": "gpt-4o",
        }
        
        response = await server._handle_start_session(message, conn)
        
        assert response["type"] == "status"
        assert response["status"] == "running"
        assert "session_id" in response
        assert conn.session_id is not None
        
        # Cleanup
        if server._sessions:
            server._sessions.close()
    
    @pytest.mark.asyncio
    async def test_handle_start_session_creates_agent(self):
        """Test that start session creates an agent."""
        from praisonai.browser.server import BrowserServer, ClientConnection
        
        server = BrowserServer()
        conn = ClientConnection(websocket=Mock())
        
        await server._handle_start_session(
            {"type": "start_session", "goal": "Test"},
            conn
        )
        
        assert conn.session_id in server._agents
        
        # Cleanup
        if server._sessions:
            server._sessions.close()


class TestIntegration:
    """Integration tests for server components."""
    
    def test_server_session_agent_integration(self):
        """Test server creates session and agent correctly."""
        from praisonai.browser.server import BrowserServer
        from praisonai.browser.sessions import SessionManager
        from praisonai.browser.agent import BrowserAgent
        
        server = BrowserServer(model="gpt-4o")
        
        # Verify all components can be imported and initialized
        assert server.model == "gpt-4o"
        
        # Test session manager
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            manager = SessionManager(f.name)
            session = manager.create_session("Test goal")
            assert session["status"] == "running"
            manager.close()
        
        # Test agent
        agent = BrowserAgent(model="gpt-4o")
        assert agent.model == "gpt-4o"
