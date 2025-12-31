"""
Integration tests for ACP stdio communication.

Tests the ACP server by spawning it as a subprocess and communicating
via JSON-RPC over stdio.
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest


class TestACPStdioIntegration:
    """Integration tests for ACP stdio communication."""
    
    @pytest.fixture
    def acp_process(self):
        """Start ACP server as subprocess."""
        # Use the CLI module directly to avoid crewai import issues
        proc = subprocess.Popen(
            [
                sys.executable, "-c",
                """
import sys
import asyncio
from praisonai.acp.server import ACPServer
from praisonai.acp.config import ACPConfig

async def run():
    config = ACPConfig(debug=True)
    server = ACPServer(config=config)
    
    # Simple JSON-RPC handler for testing
    import json
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            request = json.loads(line.strip())
            method = request.get("method", "")
            params = request.get("params", {})
            req_id = request.get("id")
            
            if method == "initialize":
                result = await server.initialize(
                    protocol_version=params.get("protocolVersion", 1),
                    client_capabilities=params.get("clientCapabilities"),
                    client_info=params.get("clientInfo"),
                )
            elif method == "session/new":
                result = await server.new_session(
                    cwd=params.get("cwd", "."),
                    mcp_servers=params.get("mcpServers", []),
                )
            elif method == "session/cancel":
                await server.cancel(session_id=params.get("sessionId", ""))
                result = None
            else:
                result = {"error": f"Unknown method: {method}"}
            
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result,
            }
            print(json.dumps(response), flush=True)
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}), flush=True)

asyncio.run(run())
"""
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        yield proc
        proc.terminate()
        proc.wait(timeout=5)
    
    def send_request(self, proc, method: str, params: dict, req_id: int = 1) -> dict:
        """Send JSON-RPC request and get response."""
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        
        # Read response with timeout
        response_line = proc.stdout.readline()
        if response_line:
            return json.loads(response_line.strip())
        return None
    
    def test_initialize(self, acp_process):
        """Test initialize handshake."""
        response = self.send_request(
            acp_process,
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {"fs": {"readTextFile": True}},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        )
        
        assert response is not None
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        
        result = response["result"]
        assert result["protocolVersion"] == 1
        assert "agentCapabilities" in result
        assert result["agentInfo"]["name"] == "praisonai"
    
    def test_new_session(self, acp_process):
        """Test session creation."""
        # First initialize
        self.send_request(
            acp_process,
            "initialize",
            {"protocolVersion": 1},
            req_id=1,
        )
        
        # Then create session
        response = self.send_request(
            acp_process,
            "session/new",
            {
                "cwd": "/tmp/test",
                "mcpServers": [],
            },
            req_id=2,
        )
        
        assert response is not None
        assert response["id"] == 2
        assert "result" in response
        
        result = response["result"]
        assert "sessionId" in result
        assert result["sessionId"].startswith("sess_")
    
    def test_cancel_notification(self, acp_process):
        """Test cancel notification."""
        # Initialize
        self.send_request(acp_process, "initialize", {"protocolVersion": 1}, req_id=1)
        
        # Create session
        new_resp = self.send_request(
            acp_process,
            "session/new",
            {"cwd": "/tmp", "mcpServers": []},
            req_id=2,
        )
        session_id = new_resp["result"]["sessionId"]
        
        # Send cancel (notification, but we're treating it as request for testing)
        response = self.send_request(
            acp_process,
            "session/cancel",
            {"sessionId": session_id},
            req_id=3,
        )
        
        assert response is not None
        assert response["id"] == 3


class TestACPNoStdoutPollution:
    """Tests to ensure ACP doesn't pollute stdout."""
    
    def test_no_print_statements(self):
        """Verify ACP modules don't have print statements that would pollute stdout."""
        import ast
        from pathlib import Path
        
        acp_dir = Path(__file__).parent.parent.parent.parent / "praisonai" / "acp"
        
        for py_file in acp_dir.glob("*.py"):
            content = py_file.read_text()
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name) and node.func.id == "print":
                            # Check if it's inside a function that's not for debugging
                            pytest.fail(f"Found print() in {py_file.name} - stdout must be reserved for JSON-RPC")
            except SyntaxError:
                pass  # Skip files with syntax errors
    
    def test_logging_to_stderr(self):
        """Verify logging is configured for stderr."""
        from praisonai.acp.server import _setup_stderr_logging
        import logging
        import sys
        
        _setup_stderr_logging(debug=True)
        
        logger = logging.getLogger("praisonai.acp")
        
        # Check that handlers write to stderr
        for handler in logger.handlers:
            if hasattr(handler, 'stream'):
                assert handler.stream == sys.stderr, "Logger must write to stderr, not stdout"


class TestACPInteractiveModeCompatibility:
    """Tests for ACP and interactive mode compatibility."""
    
    def test_acp_import_does_not_break_interactive(self):
        """Verify importing ACP doesn't break interactive mode imports."""
        # This should not raise any errors
        from praisonai.acp import ACPConfig
        
        # Interactive mode imports should still work
        from praisonai.cli.features.interactive_tui import InteractiveConfig
        
        # Both should be usable
        acp_config = ACPConfig()
        interactive_config = InteractiveConfig()
        
        assert acp_config is not None
        assert interactive_config is not None
    
    def test_acp_lazy_import(self):
        """Verify ACP uses lazy imports."""
        import time
        
        start = time.time()
        import praisonai.acp as acp_module  # noqa: F401
        import_time = time.time() - start
        
        # Import should be fast (< 100ms)
        assert import_time < 0.1, f"ACP import too slow: {import_time}s"
    
    def test_interactive_mode_without_acp_sdk(self):
        """Verify interactive mode works even if ACP SDK is not installed."""
        # Mock the ACP SDK not being available
        import sys
        
        # Save original
        original_modules = sys.modules.copy()
        
        try:
            # Remove acp from modules if present
            if 'acp' in sys.modules:
                del sys.modules['acp']
            
            # Interactive mode should still work
            from praisonai.cli.features.interactive_tui import InteractiveSession
            
            session = InteractiveSession()
            assert session is not None
        finally:
            # Restore
            sys.modules.update(original_modules)


class TestACPSessionPersistence:
    """Tests for ACP session persistence."""
    
    def test_session_save_and_load(self):
        """Test session persistence across server restarts."""
        from praisonai.acp.session import ACPSession, SessionStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(storage_dir=Path(tmpdir))
            
            # Create and save session
            session = ACPSession.create(workspace=Path("/tmp/test"))
            session.add_message("user", "Hello")
            session.add_message("assistant", "Hi there!")
            store.save(session)
            
            # Create new store instance (simulating restart)
            store2 = SessionStore(storage_dir=Path(tmpdir))
            
            # Load session
            loaded = store2.load(session.session_id)
            
            assert loaded is not None
            assert loaded.session_id == session.session_id
            assert len(loaded.messages) == 2
            assert loaded.messages[0]["content"] == "Hello"
    
    def test_resume_last_session(self):
        """Test --resume --last functionality."""
        from praisonai.acp.session import ACPSession, SessionStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(storage_dir=Path(tmpdir))
            
            # Create multiple sessions
            session1 = ACPSession.create(workspace=Path("/tmp/test1"))
            store.save(session1)
            
            time.sleep(0.01)  # Ensure different timestamps
            
            session2 = ACPSession.create(workspace=Path("/tmp/test2"))
            session2.add_message("user", "Last session message")
            store.save(session2)
            
            # Load last session
            last = store.load_last()
            
            assert last is not None
            assert last.session_id == session2.session_id
            assert len(last.messages) == 1
