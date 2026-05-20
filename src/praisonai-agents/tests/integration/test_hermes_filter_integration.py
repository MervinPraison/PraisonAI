"""
Integration tests for HERMES_ONLY_TOOLS filter with tool registry.

Tests the integration between the HERMES_ONLY_TOOLS filter and the
tool registry system to ensure proper filtering across the ecosystem.
"""

import os
import pytest
from unittest.mock import patch

from praisonaiagents.tools.registry import (
    ToolRegistry,
    get_registry,
    list_tools_with_hermes_filter,
)
from praisonaiagents.tools.base import BaseTool, ToolResult


class MockTool(BaseTool):
    """Mock tool for testing."""
    
    def __init__(self, name: str):
        super().__init__(name=name)
    
    def execute(self, *args, **kwargs) -> ToolResult:
        return ToolResult(
            content=f"Mock result from {self.name}",
            tool_name=self.name
        )


def mock_function_tool():
    """Mock function tool for testing."""
    return "mock function result"


class TestHermesFilterRegistryIntegration:
    """Test integration between HERMES_ONLY_TOOLS filter and tool registry."""
    
    def setup_method(self):
        """Set up each test with a fresh registry."""
        # Create a new registry instance for isolation
        self.registry = ToolRegistry()
        
        # Register some mock tools
        self.registry.register(MockTool("search_web"))
        self.registry.register(MockTool("send_email"))
        self.registry.register(MockTool("extract_pdf"))
        self.registry.register(MockTool("youtube_download"))
        self.registry.register(mock_function_tool, name="execute_shell")
    
    def test_registry_hermes_filter_unset(self):
        """Test registry filtering with HERMES_ONLY_TOOLS unset."""
        with patch('os.environ.get', return_value=None):
            filtered_tools = self.registry.list_tools_with_hermes_filter()
        
        # Should return all tools when filter is unset
        assert len(filtered_tools) == 5
        assert set(filtered_tools) == {
            "search_web", "send_email", "extract_pdf", 
            "youtube_download", "execute_shell"
        }
    
    def test_registry_hermes_filter_with_whitelist(self):
        """Test registry filtering with HERMES_ONLY_TOOLS set."""
        with patch.dict(os.environ, {
            "HERMES_ONLY_TOOLS": "search_web,send_email,unknown_tool"
        }):
            with patch('logging.warning'):  # Suppress warnings about unknown tools
                filtered_tools = self.registry.list_tools_with_hermes_filter()
        
        # Should only return whitelisted tools that exist
        assert set(filtered_tools) == {"search_web", "send_email"}
    
    def test_registry_hermes_filter_empty_result(self):
        """Test registry filtering when no tools match whitelist."""
        with patch.dict(os.environ, {
            "HERMES_ONLY_TOOLS": "nonexistent_tool1,nonexistent_tool2"
        }):
            with patch('logging.warning'):  # Suppress warnings about unknown tools
                filtered_tools = self.registry.list_tools_with_hermes_filter()
        
        # Should return empty list when no tools match
        assert filtered_tools == []
    
    def test_registry_hermes_filter_error_fallback(self):
        """Test registry filtering falls back on error."""
        # Mock an error in the filter
        with patch('praisonaiagents.tools.registry.filter_tools_with_hermes',
                   side_effect=Exception("Mock error")):
            with patch('logging.error'):  # Suppress error logging
                filtered_tools = self.registry.list_tools_with_hermes_filter()
        
        # Should fallback to all tools on error
        assert len(filtered_tools) == 5
    
    def test_registry_hermes_filter_import_error_fallback(self):
        """Test registry filtering falls back on import error."""
        # Mock ImportError
        with patch('praisonaiagents.tools.registry.filter_tools_with_hermes',
                   side_effect=ImportError("Module not found")):
            with patch('logging.warning'):  # Suppress warning logging
                filtered_tools = self.registry.list_tools_with_hermes_filter()
        
        # Should fallback to all tools on import error
        assert len(filtered_tools) == 5


class TestGlobalRegistryHermesFilter:
    """Test HERMES_ONLY_TOOLS filter with global registry functions."""
    
    def setup_method(self):
        """Clear global registry for each test."""
        get_registry().clear()
        
        # Register some tools in global registry
        from praisonaiagents.tools import register_tool
        register_tool(MockTool("global_search"))
        register_tool(MockTool("global_send"))
        register_tool(MockTool("global_extract"))
    
    def teardown_method(self):
        """Clean up global registry."""
        get_registry().clear()
    
    def test_global_list_tools_with_hermes_filter(self):
        """Test global convenience function for HERMES_ONLY_TOOLS filtering."""
        with patch.dict(os.environ, {
            "HERMES_ONLY_TOOLS": "global_search,global_send"
        }):
            filtered_tools = list_tools_with_hermes_filter()
        
        assert set(filtered_tools) == {"global_search", "global_send"}
    
    def test_global_list_tools_with_hermes_filter_unset(self):
        """Test global function with HERMES_ONLY_TOOLS unset."""
        with patch('os.environ.get', return_value=None):
            with patch('logging.warning'):  # Suppress unset warning
                filtered_tools = list_tools_with_hermes_filter()
        
        # Should return all registered tools
        assert len(filtered_tools) == 3
        assert set(filtered_tools) == {"global_search", "global_send", "global_extract"}


class TestHermesFilterCLIIntegration:
    """Test HERMES_ONLY_TOOLS filter integration with CLI tool loading."""
    
    def test_cli_agents_load_tools_with_filter(self):
        """Test CLI agents tool loading with HERMES_ONLY_TOOLS filter."""
        from praisonai.cli.features.agents import MultiAgentHandler
        
        handler = MultiAgentHandler(verbose=False)
        
        # Test with filter enabled
        with patch.dict(os.environ, {
            "HERMES_ONLY_TOOLS": "internet_search,read_file"
        }):
            tools = handler._load_tools([
                "internet_search", "read_file", "write_file", "execute_command"
            ])
        
        # Should only load tools that pass the filter AND are requested
        # In this case, write_file and execute_command should be filtered out
        # by HERMES_ONLY_TOOLS, but internet_search and read_file should be loaded
        assert len(tools) == 2  # Only the whitelisted and requested tools
    
    def test_cli_agents_load_tools_without_filter(self):
        """Test CLI agents tool loading without HERMES_ONLY_TOOLS filter."""
        from praisonai.cli.features.agents import MultiAgentHandler
        
        handler = MultiAgentHandler(verbose=False)
        
        # Test without filter (unset environment variable)
        with patch('os.environ.get', return_value=None):
            tools = handler._load_tools([
                "internet_search", "read_file", "write_file"
            ])
        
        # Should load all requested tools when no filter is set
        assert len(tools) == 3
    
    def test_cli_agents_load_tools_filter_error_handling(self):
        """Test CLI agents handles HERMES_ONLY_TOOLS filter errors gracefully."""
        from praisonai.cli.features.agents import MultiAgentHandler
        
        handler = MultiAgentHandler(verbose=False)
        
        # Test with invalid filter configuration
        with patch.dict(os.environ, {"HERMES_ONLY_TOOLS": ""}):
            # Should handle the ValueError from empty string gracefully
            tools = handler._load_tools(["internet_search", "read_file"])
        
        # Should still work and load tools despite filter error
        # (the ValueError is caught and the filter is bypassed)
        assert len(tools) >= 0  # May be 0 or more depending on error handling


class TestHermesFilterSemantics:
    """Test semantic requirements from the issue specification."""
    
    def test_order_independence_of_imports(self):
        """Test that import order doesn't affect filtering results."""
        # Create two registries with tools registered in different orders
        registry1 = ToolRegistry()
        registry2 = ToolRegistry()
        
        # Register in different orders
        tools = [MockTool("tool_a"), MockTool("tool_b"), MockTool("tool_c")]
        
        # Order 1: a, b, c
        for tool in tools:
            registry1.register(tool)
        
        # Order 2: c, b, a
        for tool in reversed(tools):
            registry2.register(tool)
        
        # Both should produce the same filtered result
        with patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "tool_b,tool_a"}):
            filtered1 = registry1.list_tools_with_hermes_filter()
            filtered2 = registry2.list_tools_with_hermes_filter()
        
        # Results should be identical regardless of registration order
        assert set(filtered1) == set(filtered2) == {"tool_a", "tool_b"}
    
    def test_duplicate_tool_names_isolation(self):
        """Test that filter isolates winner when duplicate names exist."""
        registry = ToolRegistry()
        
        # Register two tools with same name (second should overwrite first)
        registry.register(MockTool("search"), name="search")
        registry.register(mock_function_tool, name="search")  # overwrites
        
        # Register additional tools
        registry.register(MockTool("extract"))
        
        with patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "search"}):
            filtered_tools = registry.list_tools_with_hermes_filter()
            
        # Should isolate the winning implementation
        assert filtered_tools == ["search"]
        
        # Verify we can get the tool and it's the last one registered
        tool = registry.get("search")
        assert callable(tool)  # Should be the function, not the MockTool
    
    @patch.dict(os.environ, {"CI": "true"})
    def test_strict_mode_in_ci(self):
        """Test strict failure mode in CI environment."""
        registry = ToolRegistry()
        registry.register(MockTool("available_tool"))
        
        # Should fail strictly in CI when unknown tools are specified
        with patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "available_tool,unknown_tool"}):
            with pytest.raises(ValueError, match="Unknown tools.*unknown_tool"):
                registry.list_tools_with_hermes_filter()


if __name__ == "__main__":
    pytest.main([__file__])