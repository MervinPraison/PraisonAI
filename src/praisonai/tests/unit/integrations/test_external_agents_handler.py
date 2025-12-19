"""
Tests for ExternalAgentsHandler.

TDD approach: Write tests first, then implement.
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))


class TestExternalAgentsHandler:
    """Tests for ExternalAgentsHandler class."""
    
    def test_import_external_agents_handler(self):
        """Test that ExternalAgentsHandler can be imported."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        assert ExternalAgentsHandler is not None
    
    def test_feature_name(self):
        """Test that feature_name is correct."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        handler = ExternalAgentsHandler()
        assert handler.feature_name == "external_agents"
    
    def test_flag_name(self):
        """Test that flag_name is correct."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        handler = ExternalAgentsHandler()
        assert handler.flag_name == "external-agent"
    
    def test_supported_integrations(self):
        """Test that all integrations are supported."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        handler = ExternalAgentsHandler()
        
        assert "claude" in handler.INTEGRATIONS
        assert "gemini" in handler.INTEGRATIONS
        assert "codex" in handler.INTEGRATIONS
        assert "cursor" in handler.INTEGRATIONS
    
    def test_get_integration_claude(self):
        """Test getting Claude integration."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        from praisonai.integrations.claude_code import ClaudeCodeIntegration
        
        handler = ExternalAgentsHandler()
        integration = handler.get_integration("claude")
        
        assert isinstance(integration, ClaudeCodeIntegration)
    
    def test_get_integration_gemini(self):
        """Test getting Gemini integration."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        
        handler = ExternalAgentsHandler()
        integration = handler.get_integration("gemini")
        
        assert isinstance(integration, GeminiCLIIntegration)
    
    def test_get_integration_codex(self):
        """Test getting Codex integration."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        from praisonai.integrations.codex_cli import CodexCLIIntegration
        
        handler = ExternalAgentsHandler()
        integration = handler.get_integration("codex")
        
        assert isinstance(integration, CodexCLIIntegration)
    
    def test_get_integration_cursor(self):
        """Test getting Cursor integration."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        from praisonai.integrations.cursor_cli import CursorCLIIntegration
        
        handler = ExternalAgentsHandler()
        integration = handler.get_integration("cursor")
        
        assert isinstance(integration, CursorCLIIntegration)
    
    def test_get_integration_invalid(self):
        """Test getting invalid integration raises error."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        
        handler = ExternalAgentsHandler()
        
        with pytest.raises(ValueError):
            handler.get_integration("invalid")
    
    def test_list_integrations(self):
        """Test listing all integrations."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        
        handler = ExternalAgentsHandler()
        integrations = handler.list_integrations()
        
        assert len(integrations) == 4
        assert all(name in integrations for name in ["claude", "gemini", "codex", "cursor"])
    
    def test_check_availability(self):
        """Test checking integration availability."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        
        handler = ExternalAgentsHandler()
        availability = handler.check_availability()
        
        assert isinstance(availability, dict)
        assert "claude" in availability
        assert isinstance(availability["claude"], bool)


class TestExternalAgentsHandlerConfig:
    """Tests for ExternalAgentsHandler configuration."""
    
    def test_apply_to_agent_config_adds_tool(self):
        """Test that apply_to_agent_config adds tool to config."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        
        handler = ExternalAgentsHandler()
        config = {"tools": []}
        
        # Mock the integration to be available
        with patch.object(handler, 'get_integration') as mock_get:
            mock_integration = MagicMock()
            mock_integration.is_available = True
            mock_integration.as_tool.return_value = lambda x: x
            mock_get.return_value = mock_integration
            
            result = handler.apply_to_agent_config(config, "claude")
            
            assert len(result["tools"]) == 1
    
    def test_apply_to_agent_config_skips_unavailable(self):
        """Test that apply_to_agent_config skips unavailable integrations."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        
        handler = ExternalAgentsHandler()
        config = {"tools": []}
        
        with patch.object(handler, 'get_integration') as mock_get:
            mock_integration = MagicMock()
            mock_integration.is_available = False
            mock_get.return_value = mock_integration
            
            result = handler.apply_to_agent_config(config, "claude")
            
            assert len(result["tools"]) == 0


class TestExternalAgentsHandlerExecution:
    """Tests for ExternalAgentsHandler execution."""
    
    def test_execute_returns_integration(self):
        """Test that execute returns the integration."""
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        
        handler = ExternalAgentsHandler()
        
        with patch.object(handler, 'get_integration') as mock_get:
            mock_integration = MagicMock()
            mock_integration.is_available = True
            mock_get.return_value = mock_integration
            
            result = handler.execute(integration_name="claude")
            
            assert result == mock_integration
