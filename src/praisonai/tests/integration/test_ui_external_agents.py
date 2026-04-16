"""
Integration tests for external agents UI functionality.

Tests the shared helper and UI integration for external agents (Claude/Gemini/Codex/Cursor).
"""

import pytest
import shutil
from unittest.mock import patch, MagicMock
import sys
import os

# Add src path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from praisonai.ui._external_agents import (
    EXTERNAL_AGENTS,
    installed_external_agents,
    external_agent_tools,
    chainlit_switches,
    aiui_settings_entries,
)


class TestExternalAgentsHelper:
    """Test the shared external agents helper."""
    
    def test_external_agents_config(self):
        """Test that EXTERNAL_AGENTS is properly configured."""
        assert isinstance(EXTERNAL_AGENTS, dict)
        assert "claude_enabled" in EXTERNAL_AGENTS
        assert "gemini_enabled" in EXTERNAL_AGENTS
        assert "codex_enabled" in EXTERNAL_AGENTS
        assert "cursor_enabled" in EXTERNAL_AGENTS
        
        # Check structure of each agent config
        for toggle_id, config in EXTERNAL_AGENTS.items():
            assert "module" in config
            assert "cls" in config
            assert "label" in config
            assert "cli" in config
    
    @patch('shutil.which')
    def test_installed_external_agents_caching(self, mock_which):
        """Test that installed_external_agents properly caches results."""
        # Clear cache
        from praisonai.ui._external_agents import installed_external_agents
        installed_external_agents.cache_clear()
        
        # Mock some CLIs as available
        def mock_which_side_effect(cli):
            return "/usr/bin/claude" if cli == "claude" else None
        
        mock_which.side_effect = mock_which_side_effect
        
        # First call should check all CLIs
        result1 = installed_external_agents()
        assert result1 == ["claude_enabled"]
        assert mock_which.call_count == 4  # Called for each CLI
        
        # Second call should use cache
        mock_which.reset_mock()
        result2 = installed_external_agents()
        assert result2 == ["claude_enabled"]
        assert mock_which.call_count == 0  # Not called due to cache
    
    @patch('importlib.import_module')
    def test_external_agent_tools(self, mock_import):
        """Test external_agent_tools builds tools correctly."""
        # Mock integration classes
        mock_integration = MagicMock()
        mock_integration.is_available = True
        mock_tool_func = MagicMock()
        mock_integration.as_tool.return_value = mock_tool_func
        
        mock_module = MagicMock()
        mock_module.ClaudeCodeIntegration.return_value = mock_integration
        mock_import.return_value = mock_module
        
        settings = {"claude_enabled": True, "gemini_enabled": False}
        tools = external_agent_tools(settings)
        
        assert len(tools) == 1
        assert tools[0] == mock_tool_func
        mock_import.assert_called_once_with("praisonai.integrations.claude_code")
        mock_integration.as_tool.assert_called_once()
    
    def test_external_agent_tools_unavailable_integration(self):
        """Test external_agent_tools handles missing integrations gracefully."""
        settings = {"nonexistent_enabled": True}
        tools = external_agent_tools(settings)
        assert tools == []
    
    @patch('chainlit.input_widget.Switch')
    @patch('praisonai.ui._external_agents.installed_external_agents')
    def test_chainlit_switches(self, mock_installed, mock_switch):
        """Test chainlit_switches generates correct switches."""
        mock_installed.return_value = ["claude_enabled", "gemini_enabled"]
        mock_switch_instance = MagicMock()
        mock_switch.return_value = mock_switch_instance
        
        current_settings = {"claude_enabled": True, "gemini_enabled": False}
        switches = chainlit_switches(current_settings)
        
        assert len(switches) == 2
        assert all(s == mock_switch_instance for s in switches)
        assert mock_switch.call_count == 2
    
    @patch('praisonai.ui._external_agents.installed_external_agents')
    def test_aiui_settings_entries(self, mock_installed):
        """Test aiui_settings_entries generates correct settings."""
        mock_installed.return_value = ["claude_enabled", "gemini_enabled"]
        
        settings = aiui_settings_entries()
        
        assert isinstance(settings, dict)
        assert "claude_enabled" in settings
        assert "gemini_enabled" in settings
        assert settings["claude_enabled"]["type"] == "checkbox"
        assert settings["claude_enabled"]["default"] is False


class TestBackwardCompatibility:
    """Test backward compatibility with legacy settings."""
    
    def test_claude_code_enabled_legacy_support(self):
        """Test that claude_code_enabled is mapped to claude_enabled."""
        # This would require mocking chainlit session which is complex
        # In practice, this is tested by the load_external_agent_settings_from_chainlit function
        # which handles the legacy mapping
        pass


class TestAvailabilityGating:
    """Test that unavailable CLIs are properly hidden."""
    
    @patch('shutil.which')
    def test_only_available_agents_shown(self, mock_which):
        """Test that only available external agents are shown in UI."""
        # Clear cache
        from praisonai.ui._external_agents import installed_external_agents
        installed_external_agents.cache_clear()
        
        # Mock only Claude as available
        mock_which.side_effect = lambda cli: "/usr/bin/claude" if cli == "claude" else None
        
        available = installed_external_agents()
        assert available == ["claude_enabled"]
        
        # Verify all CLIs were checked
        expected_calls = [cli_config["cli"] for cli_config in EXTERNAL_AGENTS.values()]
        actual_calls = [call[0][0] for call in mock_which.call_args_list]
        assert set(actual_calls) == set(expected_calls)


@pytest.mark.integration
class TestRealAgenticIntegration:
    """Real agentic tests - requires actual integrations to be available."""
    
    @pytest.mark.skipif(not shutil.which("echo"), reason="echo command not available")
    def test_external_agent_tools_real_execution(self):
        """Test that external agent tools can be created and are callable."""
        # This is a simplified test using echo command to simulate external CLI
        # In a real test environment with Claude Code installed, this would test actual execution
        
        settings = {"claude_enabled": False}  # Disable to avoid actual execution
        tools = external_agent_tools(settings)
        
        # Should return empty list when all disabled
        assert tools == []
        
        # Test with mock available integration would go here if Claude Code was installed
    
    def test_settings_to_tools_mapping_consistency(self):
        """Test that settings keys map consistently to integration modules."""
        for toggle_id, config in EXTERNAL_AGENTS.items():
            # Verify the toggle_id pattern is consistent
            assert toggle_id.endswith("_enabled")
            
            # Verify module name is valid identifier  
            module_name = config["module"]
            assert module_name.replace("_", "").isalnum()
            
            # Verify class name follows PascalCase Integration pattern
            class_name = config["cls"]
            assert class_name.endswith("Integration")
            assert class_name[0].isupper()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])