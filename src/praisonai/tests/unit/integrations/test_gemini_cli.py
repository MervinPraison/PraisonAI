"""
Tests for GeminiCLIIntegration.

TDD approach: Write tests first, then implement.
"""

import pytest
import json
from unittest.mock import patch, AsyncMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))


class TestGeminiCLIIntegration:
    """Tests for GeminiCLIIntegration class."""
    
    def test_import_gemini_cli_integration(self):
        """Test that GeminiCLIIntegration can be imported."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        assert GeminiCLIIntegration is not None
    
    def test_cli_command_is_gemini(self):
        """Test that cli_command returns 'gemini'."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        integration = GeminiCLIIntegration()
        assert integration.cli_command == "gemini"
    
    def test_inherits_from_base(self):
        """Test that GeminiCLIIntegration inherits from BaseCLIIntegration."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        from praisonai.integrations.base import BaseCLIIntegration
        
        integration = GeminiCLIIntegration()
        assert isinstance(integration, BaseCLIIntegration)
    
    def test_default_options(self):
        """Test default options are set correctly."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        
        integration = GeminiCLIIntegration()
        assert integration.output_format == "json"
        assert integration.model == "gemini-2.5-pro"
    
    def test_custom_model(self):
        """Test custom model can be set."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        
        integration = GeminiCLIIntegration(model="gemini-2.5-flash")
        assert integration.model == "gemini-2.5-flash"
    
    def test_build_command_basic(self):
        """Test building basic command."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        
        integration = GeminiCLIIntegration()
        cmd = integration._build_command("Hello")
        
        assert cmd[0] == "gemini"
        assert "-p" in cmd
        assert "Hello" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
    
    def test_build_command_with_model(self):
        """Test building command with model."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        
        integration = GeminiCLIIntegration(model="gemini-2.5-flash")
        cmd = integration._build_command("Hello")
        
        assert "-m" in cmd
        assert "gemini-2.5-flash" in cmd
    
    def test_build_command_with_include_directories(self):
        """Test building command with include directories."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        
        integration = GeminiCLIIntegration(include_directories=["../lib", "../docs"])
        cmd = integration._build_command("Hello")
        
        assert "--include-directories" in cmd


class TestGeminiCLIIntegrationAsync:
    """Async tests for GeminiCLIIntegration."""
    
    @pytest.mark.asyncio
    async def test_execute_parses_json_output(self):
        """Test that execute parses JSON output correctly."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        
        integration = GeminiCLIIntegration()
        
        mock_output = json.dumps({
            "response": "Hello, world!",
            "stats": {"models": {}}
        })
        
        with patch.object(integration, 'execute_async', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_output
            result = await integration.execute("Say hello")
            
            assert "Hello, world!" in result
    
    @pytest.mark.asyncio
    async def test_execute_handles_text_output(self):
        """Test that execute handles text output format."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        
        integration = GeminiCLIIntegration(output_format="text")
        
        with patch.object(integration, 'execute_async', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = "Hello, world!"
            result = await integration.execute("Say hello")
            
            assert result == "Hello, world!"
    
    @pytest.mark.asyncio
    async def test_get_stats_returns_usage_info(self):
        """Test that get_stats returns usage information."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        
        integration = GeminiCLIIntegration()
        
        mock_output = json.dumps({
            "response": "Hello",
            "stats": {
                "models": {
                    "gemini-2.5-pro": {
                        "tokens": {"prompt": 100, "candidates": 50}
                    }
                }
            }
        })
        
        with patch.object(integration, 'execute_async', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_output
            result, stats = await integration.execute_with_stats("Say hello")
            
            assert stats is not None
            assert "models" in stats


class TestGeminiCLIEnvironment:
    """Tests for Gemini CLI environment handling."""
    
    def test_get_env_includes_google_api_key(self):
        """Test that get_env includes Google API key."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        
        integration = GeminiCLIIntegration()
        
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
            env = integration.get_env()
            assert "GOOGLE_API_KEY" in env
    
    def test_get_env_includes_gemini_api_key(self):
        """Test that get_env includes Gemini API key."""
        from praisonai.integrations.gemini_cli import GeminiCLIIntegration
        
        integration = GeminiCLIIntegration()
        
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            env = integration.get_env()
            # Should map GEMINI_API_KEY to GOOGLE_API_KEY
            assert "GOOGLE_API_KEY" in env or "GEMINI_API_KEY" in env
