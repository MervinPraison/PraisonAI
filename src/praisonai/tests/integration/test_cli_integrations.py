"""
Integration tests for CLI tool integrations.

These tests require the actual CLI tools to be installed and API keys to be set.
Run with: pytest tests/integration/test_cli_integrations.py -v

Environment variables required:
- OPENAI_API_KEY: For general testing
- ANTHROPIC_API_KEY or CLAUDE_API_KEY: For Claude Code
- GEMINI_API_KEY or GOOGLE_API_KEY: For Gemini CLI
- CURSOR_API_KEY: For Cursor CLI
"""

import pytest
import os
import asyncio
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# Skip all tests if no API keys are set or using test/invalid key
# Valid OpenAI keys start with 'sk-' and are typically 51+ characters
_api_key = os.environ.get("OPENAI_API_KEY", "")
pytestmark = pytest.mark.skipif(
    not _api_key or 
    'test' in _api_key.lower() or 
    not _api_key.startswith('sk-') or 
    len(_api_key) < 40,
    reason="OPENAI_API_KEY not set or using test/invalid key"
)


class TestIntegrationAvailability:
    """Test that integrations can be imported and checked."""
    
    def test_import_all_integrations(self):
        """Test importing all integrations."""
        from praisonai.integrations import (
            BaseCLIIntegration,
            ClaudeCodeIntegration,
            GeminiCLIIntegration,
            CodexCLIIntegration,
            CursorCLIIntegration,
        )
        
        assert BaseCLIIntegration is not None
        assert ClaudeCodeIntegration is not None
        assert GeminiCLIIntegration is not None
        assert CodexCLIIntegration is not None
        assert CursorCLIIntegration is not None
    
    def test_get_available_integrations(self):
        """Test getting available integrations."""
        from praisonai.integrations import get_available_integrations
        
        availability = get_available_integrations()
        
        assert isinstance(availability, dict)
        assert "claude" in availability
        assert "gemini" in availability
        assert "codex" in availability
        assert "cursor" in availability
        
        print("\n📊 Integration Availability:")
        for name, available in availability.items():
            status = "✅" if available else "❌"
            print(f"  {status} {name}")


class TestClaudeCodeIntegrationReal:
    """Real integration tests for Claude Code CLI."""
    
    @pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("CLAUDE_API_KEY"),
        reason="ANTHROPIC_API_KEY or CLAUDE_API_KEY not set"
    )
    def test_claude_integration_creation(self):
        """Test creating Claude Code integration."""
        from praisonai.integrations import ClaudeCodeIntegration
        
        integration = ClaudeCodeIntegration(
            workspace=".",
            output_format="json",
            skip_permissions=True
        )
        
        assert integration.cli_command == "claude"
        print(f"\n🔧 Claude CLI available: {integration.is_available}")
    
    @pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("CLAUDE_API_KEY"),
        reason="ANTHROPIC_API_KEY or CLAUDE_API_KEY not set"
    )
    def test_claude_as_tool(self):
        """Test Claude Code as agent tool."""
        from praisonai.integrations import ClaudeCodeIntegration
        
        integration = ClaudeCodeIntegration()
        tool = integration.as_tool()
        
        assert callable(tool)
        assert tool.__name__ == "claude_tool"
        print(f"\n🔧 Claude tool created: {tool.__name__}")


class TestGeminiCLIIntegrationReal:
    """Real integration tests for Gemini CLI."""
    
    @pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"),
        reason="GEMINI_API_KEY or GOOGLE_API_KEY not set"
    )
    def test_gemini_integration_creation(self):
        """Test creating Gemini CLI integration."""
        from praisonai.integrations import GeminiCLIIntegration
        
        integration = GeminiCLIIntegration(
            workspace=".",
            model="gemini-2.5-pro",
            output_format="json"
        )
        
        assert integration.cli_command == "gemini"
        assert integration.model == "gemini-2.5-pro"
        print(f"\n🔧 Gemini CLI available: {integration.is_available}")
    
    @pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"),
        reason="GEMINI_API_KEY or GOOGLE_API_KEY not set"
    )
    def test_gemini_as_tool(self):
        """Test Gemini CLI as agent tool."""
        from praisonai.integrations import GeminiCLIIntegration
        
        integration = GeminiCLIIntegration()
        tool = integration.as_tool()
        
        assert callable(tool)
        assert tool.__name__ == "gemini_tool"
        print(f"\n🔧 Gemini tool created: {tool.__name__}")


class TestCursorCLIIntegrationReal:
    """Real integration tests for Cursor CLI."""
    
    @pytest.mark.skipif(
        not os.environ.get("CURSOR_API_KEY"),
        reason="CURSOR_API_KEY not set"
    )
    def test_cursor_integration_creation(self):
        """Test creating Cursor CLI integration."""
        from praisonai.integrations import CursorCLIIntegration
        
        integration = CursorCLIIntegration(
            workspace=".",
            output_format="json",
            force=False
        )
        
        assert integration.cli_command == "cursor-agent"
        print(f"\n🔧 Cursor CLI available: {integration.is_available}")
    
    @pytest.mark.skipif(
        not os.environ.get("CURSOR_API_KEY"),
        reason="CURSOR_API_KEY not set"
    )
    def test_cursor_as_tool(self):
        """Test Cursor CLI as agent tool."""
        from praisonai.integrations import CursorCLIIntegration
        
        integration = CursorCLIIntegration()
        tool = integration.as_tool()
        
        assert callable(tool)
        assert tool.__name__ == "cursor-agent_tool"
        print(f"\n🔧 Cursor tool created: {tool.__name__}")


class TestExternalAgentsHandler:
    """Test the ExternalAgentsHandler."""
    
    def test_handler_creation(self):
        """Test creating the handler."""
        from praisonai.cli.features import ExternalAgentsHandler
        
        handler = ExternalAgentsHandler(verbose=True)
        
        assert handler.feature_name == "external_agents"
        assert handler.flag_name == "external-agent"
    
    def test_handler_list_integrations(self):
        """Test listing integrations."""
        from praisonai.cli.features import ExternalAgentsHandler
        
        handler = ExternalAgentsHandler()
        integrations = handler.list_integrations()
        
        assert "claude" in integrations
        assert "gemini" in integrations
        assert "codex" in integrations
        assert "cursor" in integrations
        
        print("\n📋 Available integrations:", integrations)
    
    def test_handler_check_availability(self):
        """Test checking availability."""
        from praisonai.cli.features import ExternalAgentsHandler
        
        handler = ExternalAgentsHandler()
        availability = handler.check_availability()
        
        print("\n📊 Handler Availability Check:")
        for name, available in availability.items():
            status = "✅" if available else "❌"
            print(f"  {status} {name}")


class TestPerformanceImpact:
    """Test that integrations don't impact performance."""
    
    def test_lazy_loading_integrations(self):
        """Test that integrations are lazy loaded."""
        import time
        
        # Measure import time
        start = time.time()
        from praisonai.integrations import BaseCLIIntegration
        import_time = time.time() - start
        
        print(f"\n⏱️ Import time: {import_time*1000:.2f}ms")
        
        # Should be fast (< 100ms)
        assert import_time < 0.1, f"Import took too long: {import_time}s"
    
    def test_lazy_loading_handler(self):
        """Test that handler is lazy loaded."""
        import time
        
        # Measure import time
        start = time.time()
        from praisonai.cli.features import ExternalAgentsHandler
        import_time = time.time() - start
        
        print(f"\n⏱️ Handler import time: {import_time*1000:.2f}ms")
        
        # Should be fast (< 100ms)
        assert import_time < 0.1, f"Import took too long: {import_time}s"
    
    def test_availability_caching(self):
        """Test that availability checks are cached."""
        import time
        from praisonai.integrations import ClaudeCodeIntegration
        
        integration = ClaudeCodeIntegration()
        
        # First check
        start = time.time()
        _ = integration.is_available
        first_time = time.time() - start
        
        # Second check (should be cached)
        start = time.time()
        _ = integration.is_available
        second_time = time.time() - start
        
        print(f"\n⏱️ First availability check: {first_time*1000:.4f}ms")
        print(f"⏱️ Second availability check: {second_time*1000:.4f}ms")
        
        # Both should be very fast (< 10ms) due to caching
        assert first_time < 0.01, f"First check too slow: {first_time}s"
        assert second_time < 0.01, f"Second check too slow: {second_time}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
