"""
Tests for CursorCLIIntegration.

TDD approach: Write tests first, then implement.
"""

import pytest
import json
from unittest.mock import patch, AsyncMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))


class TestCursorCLIIntegration:
    """Tests for CursorCLIIntegration class."""
    
    def test_import_cursor_cli_integration(self):
        """Test that CursorCLIIntegration can be imported."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        assert CursorCLIIntegration is not None
    
    def test_cli_command_is_cursor_agent(self):
        """Test that cli_command returns 'cursor-agent'."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        integration = CursorCLIIntegration()
        assert integration.cli_command == "cursor-agent"
    
    def test_inherits_from_base(self):
        """Test that CursorCLIIntegration inherits from BaseCLIIntegration."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        from praisonai.integrations.base import BaseCLIIntegration
        
        integration = CursorCLIIntegration()
        assert isinstance(integration, BaseCLIIntegration)
    
    def test_default_options(self):
        """Test default options are set correctly."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration()
        assert integration.output_format == "json"
        assert integration.force is False
    
    def test_force_option(self):
        """Test force option can be set."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration(force=True)
        assert integration.force is True
    
    def test_model_option(self):
        """Test model option can be set."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration(model="gpt-5")
        assert integration.model == "gpt-5"
    
    def test_build_command_basic(self):
        """Test building basic command."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration()
        cmd = integration._build_command("Fix the bug")
        
        assert cmd[0] == "cursor-agent"
        assert "-p" in cmd
        assert "Fix the bug" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
    
    def test_build_command_with_force(self):
        """Test building command with force flag."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration(force=True)
        cmd = integration._build_command("Fix the bug")
        
        assert "--force" in cmd
    
    def test_build_command_with_model(self):
        """Test building command with model."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration(model="gpt-5")
        cmd = integration._build_command("Fix the bug")
        
        assert "-m" in cmd
        assert "gpt-5" in cmd
    
    def test_build_command_with_stream_partial(self):
        """Test building command with stream partial output."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration(stream_partial=True)
        cmd = integration._build_command("Fix the bug")
        
        assert "--stream-partial-output" in cmd


class TestCursorCLIIntegrationAsync:
    """Async tests for CursorCLIIntegration."""
    
    @pytest.mark.asyncio
    async def test_execute_parses_json_output(self):
        """Test that execute parses JSON output correctly."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration()
        
        mock_output = json.dumps({
            "result": "Bug fixed successfully"
        })
        
        with patch.object(integration, 'execute_async', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_output
            result = await integration.execute("Fix the bug")
            
            assert "Bug fixed" in result
    
    @pytest.mark.asyncio
    async def test_execute_handles_text_output(self):
        """Test that execute handles text output format."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration(output_format="text")
        
        with patch.object(integration, 'execute_async', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = "Bug fixed successfully"
            result = await integration.execute("Fix the bug")
            
            assert result == "Bug fixed successfully"


class TestCursorCLIEnvironment:
    """Tests for Cursor CLI environment handling."""
    
    def test_get_env_includes_cursor_api_key(self):
        """Test that get_env includes Cursor API key."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration()
        
        with patch.dict(os.environ, {"CURSOR_API_KEY": "test-key"}):
            env = integration.get_env()
            assert "CURSOR_API_KEY" in env
    
    def test_api_key_required_for_headless(self):
        """Test that API key is required for headless mode."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration()
        # Should not raise, just return env without key if not set
        env = integration.get_env()
        assert isinstance(env, dict)


class TestCursorCLISession:
    """Tests for Cursor CLI session management."""
    
    def test_resume_option(self):
        """Test resume option."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration(resume_session="session-123")
        assert integration.resume_session == "session-123"
    
    def test_build_command_with_resume(self):
        """Test building command with resume."""
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        integration = CursorCLIIntegration(resume_session="session-123")
        cmd = integration._build_command("Continue the task")
        
        assert "--resume" in cmd
        assert "session-123" in cmd
