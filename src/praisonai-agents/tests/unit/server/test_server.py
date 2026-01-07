"""
Tests for the Server module.

TDD: Tests for HTTP server and SSE events.
"""

import time

from praisonaiagents.server.server import (
    ServerConfig,
    SSEClient,
    AgentServer,
)


class TestServerConfig:
    """Tests for ServerConfig."""
    
    def test_config_defaults(self):
        """Test default configuration."""
        config = ServerConfig()
        
        assert config.host == "127.0.0.1"
        assert config.port == 8765
        assert config.cors_origins == ["*"]
        assert config.auth_token is None
    
    def test_config_custom(self):
        """Test custom configuration."""
        config = ServerConfig(
            host="0.0.0.0",
            port=8080,
            auth_token="secret",
        )
        
        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.auth_token == "secret"
    
    def test_config_to_dict(self):
        """Test config serialization."""
        config = ServerConfig(auth_token="secret")
        d = config.to_dict()
        
        assert d["host"] == "127.0.0.1"
        assert d["auth_token"] == "***"  # Should be masked


class TestSSEClient:
    """Tests for SSEClient."""
    
    def test_client_creation(self):
        """Test client creation."""
        client = SSEClient("client_123")
        
        assert client.client_id == "client_123"
        assert client.connected is True
    
    def test_client_send(self):
        """Test sending event to client."""
        client = SSEClient("client_123")
        
        client.send("message", {"text": "Hello"})
        
        # Event should be in queue
        assert not client.queue.empty()
        event = client.queue.get()
        assert event["event"] == "message"
        assert event["data"] == {"text": "Hello"}
    
    def test_client_disconnect(self):
        """Test disconnecting client."""
        client = SSEClient("client_123")
        
        client.disconnect()
        
        assert client.connected is False
    
    def test_client_send_after_disconnect(self):
        """Test that send does nothing after disconnect."""
        client = SSEClient("client_123")
        client.disconnect()
        
        client.send("message", {"text": "Hello"})
        
        # Queue should be empty
        assert client.queue.empty()


class TestAgentServer:
    """Tests for AgentServer."""
    
    def test_server_creation(self):
        """Test server creation."""
        server = AgentServer(port=8080)
        
        assert server.port == 8080
        assert server.is_running is False
    
    def test_server_with_config(self):
        """Test server with config."""
        config = ServerConfig(host="0.0.0.0", port=9000)
        server = AgentServer(config=config)
        
        assert server.host == "0.0.0.0"
        assert server.port == 9000
    
    def test_server_broadcast(self):
        """Test broadcasting to clients."""
        server = AgentServer()
        
        # Add mock clients
        client1 = SSEClient("client_1")
        client2 = SSEClient("client_2")
        server._clients["client_1"] = client1
        server._clients["client_2"] = client2
        
        server.broadcast("test", {"message": "Hello"})
        
        # Both clients should have the event
        assert not client1.queue.empty()
        assert not client2.queue.empty()
    
    def test_server_client_count(self):
        """Test client count."""
        server = AgentServer()
        
        assert server.client_count == 0
        
        server._clients["client_1"] = SSEClient("client_1")
        server._clients["client_2"] = SSEClient("client_2")
        
        assert server.client_count == 2
    
    def test_server_on_event_decorator(self):
        """Test event handler decorator."""
        server = AgentServer()
        received = []
        
        @server.on_event("message")
        def handler(data):
            received.append(data)
        
        assert "message" in server._event_handlers
        assert len(server._event_handlers["message"]) == 1
    
    def test_server_stop_disconnects_clients(self):
        """Test that stop disconnects all clients."""
        server = AgentServer()
        
        client1 = SSEClient("client_1")
        client2 = SSEClient("client_2")
        server._clients["client_1"] = client1
        server._clients["client_2"] = client2
        server._running = True
        
        server.stop()
        
        assert server.client_count == 0
        assert client1.connected is False
        assert client2.connected is False
