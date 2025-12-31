"""Unit tests for ACP server."""

import asyncio
from pathlib import Path
from praisonai.acp.config import ACPConfig
from praisonai.acp.server import ACPServer


class TestACPServer:
    """Tests for ACPServer class."""
    
    def test_server_init(self):
        """Test server initialization."""
        config = ACPConfig(workspace="/tmp/test", debug=True)
        server = ACPServer(config=config)
        
        assert server.config == config
        assert server._sessions == {}
        assert server._cancelled_sessions == set()
    
    def test_server_init_default_config(self):
        """Test server initialization with default config."""
        server = ACPServer()
        
        assert server.config is not None
        assert server.config.workspace == Path.cwd()
    
    def test_initialize(self):
        """Test initialize handler."""
        server = ACPServer()
        
        result = asyncio.run(server.initialize(
            protocol_version=1,
            client_capabilities={"fs": {"readTextFile": True}},
            client_info={"name": "test-client", "version": "1.0"},
        ))
        
        assert result["protocolVersion"] == 1
        assert "agentCapabilities" in result
        assert result["agentCapabilities"]["loadSession"] is True
        assert result["agentInfo"]["name"] == "praisonai"
    
    def test_new_session(self):
        """Test new_session handler."""
        server = ACPServer()
        
        result = asyncio.run(server.new_session(
            cwd="/tmp/test_workspace",
            mcp_servers=[],
        ))
        
        assert "sessionId" in result
        assert result["sessionId"].startswith("sess_")
        assert result["sessionId"] in server._sessions
    
    def test_new_session_with_mcp_servers(self):
        """Test new_session with MCP servers."""
        server = ACPServer()
        
        mcp_servers = [
            {"name": "test", "command": "/usr/bin/test", "args": []}
        ]
        
        result = asyncio.run(server.new_session(
            cwd="/tmp/test",
            mcp_servers=mcp_servers,
        ))
        
        session = server._sessions[result["sessionId"]]
        assert session.mcp_servers == mcp_servers
    
    def test_set_session_mode(self):
        """Test set_session_mode handler."""
        server = ACPServer()
        
        # Create a session first
        new_result = asyncio.run(server.new_session(
            cwd="/tmp/test",
            mcp_servers=[],
        ))
        session_id = new_result["sessionId"]
        
        # Set mode
        result = asyncio.run(server.set_session_mode(
            mode_id="auto",
            session_id=session_id,
        ))
        
        assert result == {}
        assert server._sessions[session_id].mode == "auto"
    
    def test_cancel(self):
        """Test cancel handler."""
        server = ACPServer()
        
        # Create a session first
        new_result = asyncio.run(server.new_session(
            cwd="/tmp/test",
            mcp_servers=[],
        ))
        session_id = new_result["sessionId"]
        
        # Cancel it
        asyncio.run(server.cancel(session_id=session_id))
        
        assert session_id in server._cancelled_sessions
    
    def test_authenticate(self):
        """Test authenticate handler."""
        server = ACPServer()
        
        result = asyncio.run(server.authenticate(method_id="test"))
        
        assert result == {}
    
    def test_list_sessions(self):
        """Test list_sessions handler."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            from praisonai.acp.session import SessionStore
            server = ACPServer()
            # Use isolated session store
            server._session_store = SessionStore(storage_dir=Path(tmpdir))
            
            # Create some sessions
            asyncio.run(server.new_session(cwd="/tmp/test1", mcp_servers=[]))
            asyncio.run(server.new_session(cwd="/tmp/test2", mcp_servers=[]))
            
            result = asyncio.run(server.list_sessions())
            
            assert "sessions" in result
            assert len(result["sessions"]) == 2
    
    def test_fork_session(self):
        """Test fork_session handler."""
        server = ACPServer()
        
        # Create original session
        original = asyncio.run(server.new_session(
            cwd="/tmp/test",
            mcp_servers=[],
        ))
        original_id = original["sessionId"]
        
        # Add a message to original
        server._sessions[original_id].add_message("user", "Hello")
        
        # Fork it
        forked = asyncio.run(server.fork_session(
            cwd="/tmp/test2",
            session_id=original_id,
        ))
        
        assert forked["sessionId"] != original_id
        assert forked["sessionId"] in server._sessions
        
        # Forked session should have the message
        forked_session = server._sessions[forked["sessionId"]]
        assert len(forked_session.messages) == 1
    
    def test_extract_prompt_text(self):
        """Test prompt text extraction."""
        server = ACPServer()
        
        prompt = [
            {"type": "text", "text": "Hello world"},
            {"type": "text", "text": "How are you?"},
        ]
        
        result = server._extract_prompt_text(prompt)
        
        assert "Hello world" in result
        assert "How are you?" in result
    
    def test_extract_prompt_text_with_resource(self):
        """Test prompt text extraction with resource."""
        server = ACPServer()
        
        prompt = [
            {"type": "text", "text": "Check this file:"},
            {
                "type": "resource",
                "resource": {
                    "uri": "file:///tmp/test.py",
                    "text": "print('hello')",
                }
            },
        ]
        
        result = server._extract_prompt_text(prompt)
        
        assert "Check this file:" in result
        assert "print('hello')" in result
        assert "file:///tmp/test.py" in result
    
    def test_get_available_modes(self):
        """Test available modes."""
        server = ACPServer()
        
        modes = server._get_available_modes()
        
        assert modes is not None
        assert len(modes) >= 2
        
        mode_ids = [m["id"] for m in modes]
        assert "manual" in mode_ids
        assert "auto" in mode_ids


class TestACPServerPrompt:
    """Tests for ACPServer prompt handling."""
    
    def test_prompt_cancelled(self):
        """Test prompt with cancelled session."""
        server = ACPServer()
        
        # Create session
        new_result = asyncio.run(server.new_session(
            cwd="/tmp/test",
            mcp_servers=[],
        ))
        session_id = new_result["sessionId"]
        
        # Mark as cancelled
        server._cancelled_sessions.add(session_id)
        
        # Try to prompt
        result = asyncio.run(server.prompt(
            prompt=[{"type": "text", "text": "Hello"}],
            session_id=session_id,
        ))
        
        assert result["stopReason"] == "cancelled"
    
    def test_prompt_nonexistent_session(self):
        """Test prompt with non-existent session."""
        server = ACPServer()
        
        result = asyncio.run(server.prompt(
            prompt=[{"type": "text", "text": "Hello"}],
            session_id="nonexistent",
        ))
        
        assert result["stopReason"] == "refusal"
