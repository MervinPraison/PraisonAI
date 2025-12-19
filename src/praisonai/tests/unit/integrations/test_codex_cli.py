"""
Tests for CodexCLIIntegration.

TDD approach: Write tests first, then implement.
"""

import pytest
import json
from unittest.mock import patch, AsyncMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))


class TestCodexCLIIntegration:
    """Tests for CodexCLIIntegration class."""
    
    def test_import_codex_cli_integration(self):
        """Test that CodexCLIIntegration can be imported."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        assert CodexCLIIntegration is not None
    
    def test_cli_command_is_codex(self):
        """Test that cli_command returns 'codex'."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        integration = CodexCLIIntegration()
        assert integration.cli_command == "codex"
    
    def test_inherits_from_base(self):
        """Test that CodexCLIIntegration inherits from BaseCLIIntegration."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        from praisonai.integrations.base import BaseCLIIntegration
        
        integration = CodexCLIIntegration()
        assert isinstance(integration, BaseCLIIntegration)
    
    def test_default_options(self):
        """Test default options are set correctly."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        
        integration = CodexCLIIntegration()
        assert integration.full_auto is False
        assert integration.sandbox == "default"
    
    def test_full_auto_option(self):
        """Test full_auto option can be set."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        
        integration = CodexCLIIntegration(full_auto=True)
        assert integration.full_auto is True
    
    def test_sandbox_option(self):
        """Test sandbox option can be set."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        
        integration = CodexCLIIntegration(sandbox="danger-full-access")
        assert integration.sandbox == "danger-full-access"
    
    def test_build_command_basic(self):
        """Test building basic command."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        
        integration = CodexCLIIntegration()
        cmd = integration._build_command("Fix the bug")
        
        assert cmd[0] == "codex"
        assert "exec" in cmd
        assert "Fix the bug" in cmd
    
    def test_build_command_with_full_auto(self):
        """Test building command with full_auto."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        
        integration = CodexCLIIntegration(full_auto=True)
        cmd = integration._build_command("Fix the bug")
        
        assert "--full-auto" in cmd
    
    def test_build_command_with_json(self):
        """Test building command with JSON output."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        
        integration = CodexCLIIntegration(json_output=True)
        cmd = integration._build_command("Fix the bug")
        
        assert "--json" in cmd
    
    def test_build_command_with_sandbox(self):
        """Test building command with sandbox."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        
        integration = CodexCLIIntegration(sandbox="danger-full-access")
        cmd = integration._build_command("Fix the bug")
        
        assert "--sandbox" in cmd
        assert "danger-full-access" in cmd


class TestCodexCLIIntegrationAsync:
    """Async tests for CodexCLIIntegration."""
    
    @pytest.mark.asyncio
    async def test_execute_returns_result(self):
        """Test that execute returns the result."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        
        integration = CodexCLIIntegration()
        
        with patch.object(integration, 'execute_async', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = "Task completed successfully"
            result = await integration.execute("Fix the bug")
            
            assert "Task completed" in result
    
    @pytest.mark.asyncio
    async def test_execute_parses_json_events(self):
        """Test that execute parses JSON events when json_output is True."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        
        integration = CodexCLIIntegration(json_output=True)
        
        mock_output = '\n'.join([
            '{"type":"thread.started","thread_id":"123"}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"Done"}}',
            '{"type":"turn.completed"}'
        ])
        
        with patch.object(integration, 'execute_async', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_output
            result = await integration.execute("Fix the bug")
            
            assert "Done" in result


class TestCodexCLIStructuredOutput:
    """Tests for Codex CLI structured output."""
    
    def test_output_schema_option(self):
        """Test output_schema option."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        
        integration = CodexCLIIntegration(output_schema="/path/to/schema.json")
        assert integration.output_schema == "/path/to/schema.json"
    
    def test_build_command_with_output_schema(self):
        """Test building command with output schema."""
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        
        integration = CodexCLIIntegration(output_schema="/path/to/schema.json")
        cmd = integration._build_command("Extract metadata")
        
        assert "--output-schema" in cmd
        assert "/path/to/schema.json" in cmd
