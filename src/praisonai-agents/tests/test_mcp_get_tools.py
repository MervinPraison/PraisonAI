"""
TDD Tests for MCP.get_tools() method.

These tests verify that the MCP class has a get_tools() method
that returns the list of tool functions.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestMCPGetTools:
    """Test MCP.get_tools() method."""
    
    def test_get_tools_method_exists(self):
        """Test that MCP class has get_tools method."""
        from praisonaiagents.mcp.mcp import MCP
        assert hasattr(MCP, 'get_tools'), "MCP class should have get_tools method"
    
    def test_get_tools_returns_list(self):
        """Test that get_tools returns a list."""
        from praisonaiagents.mcp.mcp import MCP
        
        # Create a mock MCP instance without actually connecting
        with patch.object(MCP, '__init__', lambda self: None):
            mcp = MCP.__new__(MCP)
            mcp._tools = [lambda x: x, lambda y: y]
            
            result = mcp.get_tools()
            
            assert isinstance(result, list), "get_tools should return a list"
            assert len(result) == 2, "get_tools should return all tools"
    
    def test_get_tools_returns_same_as_iter(self):
        """Test that get_tools returns same tools as __iter__."""
        from praisonaiagents.mcp.mcp import MCP
        
        with patch.object(MCP, '__init__', lambda self: None):
            mcp = MCP.__new__(MCP)
            tool1 = lambda x: x
            tool2 = lambda y: y
            mcp._tools = [tool1, tool2]
            
            get_tools_result = mcp.get_tools()
            iter_result = list(mcp)
            
            assert get_tools_result == iter_result, "get_tools should return same as __iter__"
    
    def test_get_tools_returns_empty_list_when_no_tools(self):
        """Test that get_tools returns empty list when no tools."""
        from praisonaiagents.mcp.mcp import MCP
        
        with patch.object(MCP, '__init__', lambda self: None):
            mcp = MCP.__new__(MCP)
            mcp._tools = []
            
            result = mcp.get_tools()
            
            assert result == [], "get_tools should return empty list when no tools"
    
    def test_get_tools_returns_callable_items(self):
        """Test that get_tools returns callable items."""
        from praisonaiagents.mcp.mcp import MCP
        
        with patch.object(MCP, '__init__', lambda self: None):
            mcp = MCP.__new__(MCP)
            mcp._tools = [lambda x: x, lambda y: y]
            
            result = mcp.get_tools()
            
            for tool in result:
                assert callable(tool), "Each tool should be callable"


class TestMCPGetToolsIntegration:
    """Integration tests for get_tools with real MCP initialization."""
    
    @pytest.mark.skipif(
        True,  # Skip by default - requires MCP server
        reason="Requires MCP server to be running"
    )
    def test_get_tools_with_real_mcp(self):
        """Test get_tools with real MCP server."""
        from praisonaiagents.mcp import MCP
        
        # This would require a real MCP server
        mcp = MCP("uvx mcp-server-time", timeout=30)
        tools = mcp.get_tools()
        
        assert isinstance(tools, list)
        assert len(tools) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
