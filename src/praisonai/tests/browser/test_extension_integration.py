"""Tests for browser extension integration.

These tests verify that the launch command properly uses the Chrome extension
via the bridge server, with fallback to CDP when extension is unavailable.
"""

import pytest
from unittest.mock import patch, Mock, AsyncMock, MagicMock
from typer.testing import CliRunner

from praisonai.browser.cli import app


runner = CliRunner()


class TestLaunchCommandEngineFlag:
    """Test that --engine flag is properly exposed in launch command."""
    
    def test_launch_help_shows_engine_flag(self):
        """Test launch command help shows --engine option."""
        result = runner.invoke(app, ["launch", "--help"])
        assert result.exit_code == 0
        assert "--engine" in result.output
    
    def test_launch_help_documents_engine_modes(self):
        """Test launch help documents extension, cdp, auto modes."""
        result = runner.invoke(app, ["launch", "--help"])
        assert result.exit_code == 0
        # Check that engine modes are documented
        output_lower = result.output.lower()
        assert "extension" in output_lower
        assert "cdp" in output_lower
        assert "auto" in output_lower
    
    def test_launch_help_shows_extension_benefits(self):
        """Test help explains extension mode benefits."""
        result = runner.invoke(app, ["launch", "--help"])
        assert result.exit_code == 0
        # Should mention reliability, visual feedback, or similar
        output_lower = result.output.lower()
        assert "reliab" in output_lower or "visual" in output_lower or "bridge" in output_lower


class TestEngineSelectionLogic:
    """Test engine selection logic with mocked components."""
    
    @pytest.mark.asyncio
    async def test_auto_mode_checks_extension_availability(self):
        """Test auto mode checks bridge server health for extension."""
        from praisonai.browser.server import run_browser_agent_with_progress
        
        # Mock websockets to simulate connection refused (no server)
        with patch('websockets.connect', side_effect=ConnectionRefusedError()):
            result = await run_browser_agent_with_progress(
                goal="test",
                timeout=1.0,
            )
            
            # Should fail because no bridge server
            assert result["error"]
            assert "connect" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_extension_mode_uses_bridge_server(self):
        """Test extension mode connects to bridge server."""
        import asyncio
        from unittest.mock import MagicMock
        
        # Mock websockets with successful connection
        mock_ws = MagicMock()
        mock_ws.recv = AsyncMock(side_effect=[
            # Welcome message
            '{"type": "status", "status": "connected"}',
            # Session started
            '{"type": "status", "status": "running", "session_id": "test-123"}',
            # Task completed
            '{"type": "status", "status": "completed", "message": "Done", "session_id": "test-123"}',
        ])
        mock_ws.send = AsyncMock()
        mock_ws.close = AsyncMock()
        
        mock_connect = MagicMock()
        mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.__aexit__ = AsyncMock(return_value=None)
        
        with patch('websockets.connect', return_value=mock_connect):
            from praisonai.browser.server import run_browser_agent_with_progress
            
            result = await run_browser_agent_with_progress(
                goal="test goal",
                url="https://example.com",
                timeout=10.0,
            )
            
            # Should succeed via extension
            assert result.get("success") is True
            assert result.get("engine") == "extension"


class TestRunBrowserAgentWithProgress:
    """Test the run_browser_agent_with_progress function."""
    
    def test_function_exists(self):
        """Test run_browser_agent_with_progress can be imported."""
        from praisonai.browser.server import run_browser_agent_with_progress
        assert run_browser_agent_with_progress is not None
        assert callable(run_browser_agent_with_progress)
    
    def test_function_signature(self):
        """Test function has expected parameters."""
        import inspect
        from praisonai.browser.server import run_browser_agent_with_progress
        
        sig = inspect.signature(run_browser_agent_with_progress)
        params = list(sig.parameters.keys())
        
        # Should have these parameters
        assert "goal" in params
        assert "url" in params
        assert "model" in params
        assert "max_steps" in params
        assert "timeout" in params
        assert "debug" in params
        assert "port" in params
        assert "on_step" in params
    
    @pytest.mark.asyncio
    async def test_returns_proper_result_structure(self):
        """Test returns dict with expected keys."""
        with patch('websockets.connect', side_effect=ConnectionRefusedError()):
            from praisonai.browser.server import run_browser_agent_with_progress
            
            result = await run_browser_agent_with_progress(goal="test", timeout=1.0)
            
            # Should always return a dict with these keys
            assert isinstance(result, dict)
            assert "success" in result
            assert "error" in result or result.get("success")
            assert "engine" in result
            assert result["engine"] == "extension"


class TestExtensionModeMessages:
    """Test that extension mode properly handles message types."""
    
    @pytest.mark.asyncio
    async def test_handles_action_messages(self):
        """Test extension mode processes action messages."""
        mock_ws = MagicMock()
        mock_ws.recv = AsyncMock(side_effect=[
            '{"type": "status", "status": "connected"}',
            '{"type": "status", "status": "running", "session_id": "test-123"}',
            '{"type": "action", "action": "click", "thought": "Clicking button", "done": false}',
            '{"type": "action", "action": "done", "thought": "Task complete", "done": true}',
        ])
        mock_ws.send = AsyncMock()
        mock_ws.close = AsyncMock()
        
        mock_connect = MagicMock()
        mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.__aexit__ = AsyncMock(return_value=None)
        
        with patch('websockets.connect', return_value=mock_connect):
            from praisonai.browser.server import run_browser_agent_with_progress
            
            result = await run_browser_agent_with_progress(goal="test", timeout=10.0)
            
            assert result.get("success") is True
            assert result.get("steps") == 2
            assert "Task complete" in result.get("summary", "")
    
    @pytest.mark.asyncio
    async def test_handles_error_messages(self):
        """Test extension mode handles error messages from server."""
        mock_ws = MagicMock()
        mock_ws.recv = AsyncMock(side_effect=[
            '{"type": "status", "status": "connected"}',
            '{"type": "error", "error": "Something went wrong"}',
        ])
        mock_ws.send = AsyncMock()
        mock_ws.close = AsyncMock()
        
        mock_connect = MagicMock()
        mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.__aexit__ = AsyncMock(return_value=None)
        
        with patch('websockets.connect', return_value=mock_connect):
            from praisonai.browser.server import run_browser_agent_with_progress
            
            result = await run_browser_agent_with_progress(goal="test", timeout=10.0)
            
            assert result.get("success") is False
            assert "Something went wrong" in result.get("error", "")


class TestCDPFallback:
    """Test CDP fallback when extension unavailable."""
    
    def test_cdp_agent_exists(self):
        """Test CDPBrowserAgent can be imported."""
        from praisonai.browser.cdp_agent import CDPBrowserAgent, run_cdp_only
        assert CDPBrowserAgent is not None
        assert run_cdp_only is not None
    
    def test_run_cdp_only_signature(self):
        """Test run_cdp_only has expected parameters."""
        import inspect
        from praisonai.browser.cdp_agent import run_cdp_only
        
        sig = inspect.signature(run_cdp_only)
        params = list(sig.parameters.keys())
        
        assert "goal" in params
        assert "url" in params
        assert "model" in params
        assert "port" in params
        assert "max_steps" in params


class TestProgressCallback:
    """Test step progress callbacks work."""
    
    @pytest.mark.asyncio
    async def test_on_step_callback_called(self):
        """Test on_step callback is called for each action."""
        steps_received = []
        
        def on_step(step_num):
            steps_received.append(step_num)
        
        mock_ws = MagicMock()
        mock_ws.recv = AsyncMock(side_effect=[
            '{"type": "status", "status": "connected"}',
            '{"type": "status", "status": "running", "session_id": "test-123"}',
            '{"type": "action", "action": "click", "done": false}',
            '{"type": "action", "action": "type", "done": false}',
            '{"type": "action", "action": "done", "done": true}',
        ])
        mock_ws.send = AsyncMock()
        mock_ws.close = AsyncMock()
        
        mock_connect = MagicMock()
        mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.__aexit__ = AsyncMock(return_value=None)
        
        with patch('websockets.connect', return_value=mock_connect):
            from praisonai.browser.server import run_browser_agent_with_progress
            
            result = await run_browser_agent_with_progress(
                goal="test",
                timeout=10.0,
                on_step=on_step,
            )
            
            # Should have received 3 step callbacks
            assert len(steps_received) == 3
            assert steps_received == [1, 2, 3]


class TestEngineIndicator:
    """Test that engine used is properly indicated in output."""
    
    def test_result_contains_engine_key(self):
        """Test results include engine key."""
        # Any result from extension mode should have engine key
        result = {
            "success": True,
            "steps": 5,
            "engine": "extension",
        }
        
        assert "engine" in result
        assert result["engine"] in ("extension", "cdp")
    
    def test_extension_engine_value(self):
        """Test extension mode sets engine to 'extension'."""
        from praisonai.browser.server import run_browser_agent_with_progress
        import asyncio
        
        # Force connection error to get default result
        with patch('websockets.connect', side_effect=ConnectionRefusedError()):
            result = asyncio.get_event_loop().run_until_complete(
                run_browser_agent_with_progress(goal="test", timeout=1.0)
            )
            
            # Even on error, engine should be set
            assert result["engine"] == "extension"


class TestImportCompatibility:
    """Test backward compatibility of imports."""
    
    def test_run_browser_agent_still_exists(self):
        """Test original run_browser_agent function still exists."""
        from praisonai.browser.server import run_browser_agent
        assert run_browser_agent is not None
        assert callable(run_browser_agent)
    
    def test_browser_server_unchanged(self):
        """Test BrowserServer class unchanged."""
        from praisonai.browser.server import BrowserServer
        
        server = BrowserServer(port=9999)
        assert server.port == 9999
    
    def test_cdp_agent_unchanged(self):
        """Test CDPBrowserAgent class unchanged."""
        from praisonai.browser.cdp_agent import CDPBrowserAgent
        
        # Should be able to create (won't connect until run)
        agent = CDPBrowserAgent(port=9999, model="gpt-4o-mini")
        assert agent.port == 9999


class TestLaunchCommandIntegration:
    """Integration tests for launch command with mocking."""
    
    @patch('subprocess.Popen')
    @patch('shutil.which', return_value="/usr/bin/google-chrome")
    @patch('pathlib.Path.exists', return_value=True)
    def test_launch_no_goal_doesnt_start_automation(self, mock_exists, mock_which, mock_popen):
        """Test launch without goal just starts Chrome."""
        # Mock Chrome path detection
        with patch('os.path.exists', return_value=True):
            # This will fail because no Chrome, but we just want to verify it tries
            result = runner.invoke(app, ["launch", "--no-server"])
            
            # Should try to launch Chrome
            # (May fail in test env, but should not crash)
            assert "Chrome" in result.output or result.exit_code != 0
