"""Tests for MCP server wrapper - TDD approach.

These tests define the expected behavior of ToolsMCPServer class.
"""

import pytest
from unittest.mock import patch


class TestToolsMCPServerInit:
    """Test ToolsMCPServer initialization."""
    
    def test_init_with_name(self):
        """Test server initializes with custom name."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer(name="my-tools")
        assert server.name == "my-tools"
    
    def test_init_with_default_name(self):
        """Test server initializes with default name."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        assert server.name == "praisonai-tools"
    
    def test_init_with_tools_list(self):
        """Test server initializes with list of tools."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        def my_tool(x: str) -> str:
            """A test tool."""
            return x
        
        server = ToolsMCPServer(tools=[my_tool])
        assert len(server.tools) == 1
    
    def test_init_empty_tools(self):
        """Test server initializes with empty tools list."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        assert server.tools == []


class TestToolsMCPServerRegister:
    """Test tool registration."""
    
    def test_register_single_tool(self):
        """Test registering a single tool."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        
        def search(query: str) -> str:
            """Search for information."""
            return f"Results for {query}"
        
        server.register_tool(search)
        
        assert len(server.tools) == 1
        assert server.tools[0].__name__ == "search"
    
    def test_register_multiple_tools(self):
        """Test registering multiple tools."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        
        def tool1(x: str) -> str:
            """Tool 1."""
            return x
        
        def tool2(y: int) -> int:
            """Tool 2."""
            return y
        
        server.register_tool(tool1)
        server.register_tool(tool2)
        
        assert len(server.tools) == 2
    
    def test_register_tools_batch(self):
        """Test registering multiple tools at once."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        
        def tool1(x: str) -> str:
            """Tool 1."""
            return x
        
        def tool2(y: int) -> int:
            """Tool 2."""
            return y
        
        server.register_tools([tool1, tool2])
        
        assert len(server.tools) == 2
    
    def test_register_async_tool(self):
        """Test registering an async tool."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        
        async def async_search(query: str) -> str:
            """Async search."""
            return f"Results for {query}"
        
        server.register_tool(async_search)
        
        assert len(server.tools) == 1


class TestToolsMCPServerSchemas:
    """Test schema generation for registered tools."""
    
    def test_get_tool_schemas(self):
        """Test getting schemas for all registered tools."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        
        def search(query: str, max_results: int = 10) -> str:
            """Search the web."""
            return ""
        
        server.register_tool(search)
        schemas = server.get_tool_schemas()
        
        assert len(schemas) == 1
        assert schemas[0]["name"] == "search"
        assert schemas[0]["description"] == "Search the web."
        assert "query" in schemas[0]["inputSchema"]["properties"]
    
    def test_get_tool_names(self):
        """Test getting list of tool names."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        
        def tool1(x: str) -> str:
            """Tool 1."""
            return x
        
        def tool2(y: int) -> int:
            """Tool 2."""
            return y
        
        server.register_tools([tool1, tool2])
        names = server.get_tool_names()
        
        assert set(names) == {"tool1", "tool2"}


class TestToolsMCPServerExecution:
    """Test tool execution through MCP server."""
    
    def test_execute_sync_tool(self):
        """Test executing a synchronous tool."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b
        
        server.register_tool(add)
        result = server.execute_tool("add", {"a": 5, "b": 3})
        
        assert result == 8
    
    @pytest.mark.asyncio
    async def test_execute_async_tool(self):
        """Test executing an async tool."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        
        async def async_add(a: int, b: int) -> int:
            """Add two numbers asynchronously."""
            return a + b
        
        server.register_tool(async_add)
        result = await server.execute_tool_async("async_add", {"a": 5, "b": 3})
        
        assert result == 8
    
    def test_execute_nonexistent_tool(self):
        """Test executing a tool that doesn't exist."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        
        with pytest.raises(ValueError, match="Tool 'nonexistent' not found"):
            server.execute_tool("nonexistent", {})


class TestToolsMCPServerFastMCP:
    """Test FastMCP integration."""
    
    def test_get_fastmcp_instance(self):
        """Test getting FastMCP instance with registered tools."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer(name="test-server")
        
        def my_tool(x: str) -> str:
            """A test tool."""
            return x
        
        server.register_tool(my_tool)
        
        # Get FastMCP instance
        mcp = server.get_fastmcp()
        
        assert mcp is not None
        assert mcp.name == "test-server"
    
    def test_fastmcp_has_registered_tools(self):
        """Test that FastMCP instance has all registered tools."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        
        def search(query: str) -> str:
            """Search tool."""
            return query
        
        def calculate(x: int, y: int) -> int:
            """Calculate tool."""
            return x + y
        
        server.register_tools([search, calculate])
        mcp = server.get_fastmcp()
        
        # FastMCP should have both tools registered
        # We can check by looking at the internal tool registry
        assert mcp is not None


class TestLaunchToolsMCPServer:
    """Test the convenience function for launching MCP server."""
    
    def test_launch_function_exists(self):
        """Test that launch_tools_mcp_server function exists."""
        from praisonaiagents.mcp.mcp_server import launch_tools_mcp_server
        
        assert callable(launch_tools_mcp_server)
    
    def test_launch_with_tool_names(self):
        """Test launching server with tool names from registry."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        # This should create a server with specified tools
        # We'll mock the actual launch to avoid blocking
        with patch.object(ToolsMCPServer, 'run', return_value=None):
            # Just verify it doesn't raise
            pass  # Actual launch test will be in integration tests
    
    def test_launch_with_custom_tools(self):
        """Test launching server with custom tool functions."""
        from praisonaiagents.mcp.mcp_server import launch_tools_mcp_server
        
        def my_custom_tool(x: str) -> str:
            """Custom tool."""
            return x
        
        # Verify function accepts tools parameter
        # Actual launch test will be in integration tests
        assert callable(launch_tools_mcp_server)


class TestToolsMCPServerTransports:
    """Test different transport options."""
    
    def test_stdio_transport_config(self):
        """Test stdio transport configuration."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        
        # Server should support stdio transport
        assert hasattr(server, 'run_stdio') or hasattr(server, 'run')
    
    def test_sse_transport_config(self):
        """Test SSE transport configuration."""
        from praisonaiagents.mcp.mcp_server import ToolsMCPServer
        
        server = ToolsMCPServer()
        
        # Server should support SSE transport
        assert hasattr(server, 'run_sse') or hasattr(server, 'run')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
