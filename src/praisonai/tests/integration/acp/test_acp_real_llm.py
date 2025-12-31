"""
Real LLM integration tests for ACP.

These tests use actual API keys to verify end-to-end functionality.
API keys should be set via environment variables.
"""

import os
import tempfile
from pathlib import Path

import pytest

# Skip if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)


class TestACPRealLLM:
    """Real LLM tests for ACP server."""
    
    @pytest.fixture
    def acp_server(self):
        """Create ACP server with real agent."""
        from praisonai.acp.server import ACPServer
        from praisonai.acp.config import ACPConfig
        
        config = ACPConfig(
            workspace=Path(tempfile.mkdtemp()),
            debug=True,
            model="gpt-4o-mini",
        )
        return ACPServer(config=config)
    
    @pytest.mark.asyncio
    async def test_initialize_real(self, acp_server):
        """Test real initialize handshake."""
        result = await acp_server.initialize(
            protocol_version=1,
            client_capabilities={"fs": {"readTextFile": True}},
            client_info={"name": "test-harness", "version": "1.0"},
        )
        
        assert result["protocolVersion"] == 1
        assert result["agentInfo"]["name"] == "praisonai"
        assert "agentCapabilities" in result
        
        # Log for verification (masked)
        print(f"[TEST] Initialize successful: protocol={result['protocolVersion']}")
    
    @pytest.mark.asyncio
    async def test_session_lifecycle(self, acp_server):
        """Test complete session lifecycle."""
        # Initialize
        await acp_server.initialize(protocol_version=1)
        
        # Create session
        session_result = await acp_server.new_session(
            cwd="/tmp/test",
            mcp_servers=[],
        )
        
        session_id = session_result["sessionId"]
        assert session_id.startswith("sess_")
        
        # Log for verification
        print(f"[TEST] Session created: {session_id[:20]}...")
        
        # Set mode
        await acp_server.set_session_mode(
            mode_id="manual",
            session_id=session_id,
        )
        
        # Cancel
        await acp_server.cancel(session_id=session_id)
        
        print("[TEST] Session lifecycle complete")
    
    @pytest.mark.asyncio
    async def test_prompt_with_real_llm(self, acp_server):
        """Test prompt with real LLM call."""
        # Initialize
        await acp_server.initialize(protocol_version=1)
        
        # Create session
        session_result = await acp_server.new_session(
            cwd="/tmp/test",
            mcp_servers=[],
        )
        session_id = session_result["sessionId"]
        
        # Send a simple prompt
        prompt_result = await acp_server.prompt(
            prompt=[{"type": "text", "text": "What is 2+2? Reply with just the number."}],
            session_id=session_id,
        )
        
        # Verify response
        assert "stopReason" in prompt_result
        assert prompt_result["stopReason"] in ["end_turn", "cancelled", "refusal"]
        
        # Log for verification (no secrets)
        print(f"[TEST] Prompt completed: stopReason={prompt_result['stopReason']}")
        print(f"[TEST] Session: {session_id[:20]}...")
    
    @pytest.mark.asyncio
    async def test_session_resume(self, acp_server):
        """Test session resume functionality."""
        # Initialize
        await acp_server.initialize(protocol_version=1)
        
        # Create session
        session_result = await acp_server.new_session(
            cwd="/tmp/test",
            mcp_servers=[],
        )
        session_id = session_result["sessionId"]
        
        # Add a message to the session
        acp_server._sessions[session_id].add_message("user", "Test message")
        acp_server._session_store.save(acp_server._sessions[session_id])
        
        # Create new server instance (simulating restart)
        from praisonai.acp.config import ACPConfig
        config = ACPConfig(workspace=Path("/tmp/test"), debug=True)
        from praisonai.acp.server import ACPServer as ACPServerClass
        new_server = ACPServerClass(config=config)
        
        # Resume session
        resume_result = await new_server.load_session(
            cwd="/tmp/test",
            mcp_servers=[],
            session_id=session_id,
        )
        
        assert resume_result is not None
        assert session_id in new_server._sessions
        
        # Verify message was preserved
        loaded_session = new_server._sessions[session_id]
        assert len(loaded_session.messages) == 1
        assert loaded_session.messages[0]["content"] == "Test message"
        
        print(f"[TEST] Session resume successful: {session_id[:20]}...")


class TestACPPermissionGating:
    """Tests for permission gating."""
    
    def test_read_only_default(self):
        """Verify read-only is default."""
        from praisonai.acp.config import ACPConfig
        
        config = ACPConfig()
        assert config.read_only is True
        assert config.can_write() is False
        assert config.can_execute_shell() is False
    
    def test_explicit_write_permission(self):
        """Test explicit write permission."""
        from praisonai.acp.config import ACPConfig
        
        config = ACPConfig(allow_write=True)
        assert config.can_write() is True
    
    def test_workspace_boundary(self):
        """Test workspace boundary enforcement."""
        from praisonai.acp.config import ACPConfig
        
        config = ACPConfig(workspace="/tmp/test_workspace")
        
        # Within workspace - allowed
        assert config.is_path_allowed(Path("/tmp/test_workspace/file.txt"))
        assert config.is_path_allowed(Path("/tmp/test_workspace/subdir/file.txt"))
        
        # Outside workspace - not allowed
        assert not config.is_path_allowed(Path("/etc/passwd"))
        assert not config.is_path_allowed(Path("/var/log/system.log"))


class TestACPTracing:
    """Tests for tracing and attribution."""
    
    def test_session_has_trace_ids(self):
        """Verify sessions have trace IDs."""
        from praisonai.acp.session import ACPSession
        
        session = ACPSession.create(
            workspace=Path("/tmp/test"),
            agent_id="test_agent",
        )
        
        assert session.session_id is not None
        assert session.run_id is not None
        assert session.trace_id is not None
        assert session.agent_id == "test_agent"
        
        # IDs should have proper prefixes
        assert session.session_id.startswith("sess_")
        assert session.run_id.startswith("run_")
        assert session.trace_id.startswith("trace_")
        
        print(f"[TEST] Trace IDs: session={session.session_id[:15]}, run={session.run_id}, trace={session.trace_id}")
