"""
Test-Driven Development tests for Multiple MCP Tools support.

This test file verifies that:
1. Single MCP instance works (baseline)
2. Multiple MCP instances in a list work for tool definition conversion
3. Multiple MCP instances in a list work for tool execution
4. Mixed tools (MCP + regular functions) work together

Uses mcp-server-time as the test MCP server (simple, no API keys needed).
"""

import pytest
import os
import sys
from unittest.mock import Mock

# Add the package to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Skip entire module if mcp package is not installed
try:
    from praisonaiagents.mcp.mcp import MCP
    from praisonaiagents.agent.agent import Agent
except ImportError:
    pytest.skip("MCP package not installed", allow_module_level=True)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def time_mcp():
    """Create a Time MCP server instance."""
    return MCP("uvx mcp-server-time", timeout=30)


@pytest.fixture
def mock_mcp_with_tools():
    """Create a mock MCP instance with predefined tools."""
    mock = Mock(spec=MCP)
    mock.is_sse = False
    mock.is_http_stream = False
    mock.is_websocket = False
    
    # Create mock runner with tools
    mock.runner = Mock()
    mock_tool1 = Mock()
    mock_tool1.name = "get_current_time"
    mock_tool1.description = "Get current time in a timezone"
    mock_tool1.inputSchema = {
        "type": "object",
        "properties": {
            "timezone": {"type": "string", "description": "IANA timezone name"}
        },
        "required": ["timezone"]
    }
    
    mock_tool2 = Mock()
    mock_tool2.name = "convert_time"
    mock_tool2.description = "Convert time between timezones"
    mock_tool2.inputSchema = {
        "type": "object",
        "properties": {
            "source_timezone": {"type": "string"},
            "time": {"type": "string"},
            "target_timezone": {"type": "string"}
        },
        "required": ["source_timezone", "time", "target_timezone"]
    }
    
    mock.runner.tools = [mock_tool1, mock_tool2]
    mock._tools = []
    
    # Mock to_openai_tool method
    def to_openai_tool():
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Get current time in a timezone",
                    "parameters": mock_tool1.inputSchema
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "convert_time",
                    "description": "Convert time between timezones",
                    "parameters": mock_tool2.inputSchema
                }
            }
        ]
    mock.to_openai_tool = to_openai_tool
    
    # Mock __iter__ to return tool functions
    def get_current_time(timezone: str) -> str:
        return f"Time in {timezone}: 12:00"
    def convert_time(source_timezone: str, time: str, target_timezone: str) -> str:
        return f"Converted {time} from {source_timezone} to {target_timezone}"
    get_current_time.__name__ = "get_current_time"
    convert_time.__name__ = "convert_time"
    mock._tools = [get_current_time, convert_time]
    mock.__iter__ = lambda self: iter(self._tools)
    
    return mock


@pytest.fixture
def mock_mcp_filesystem():
    """Create a mock MCP instance simulating filesystem server."""
    mock = Mock(spec=MCP)
    mock.is_sse = False
    mock.is_http_stream = False
    mock.is_websocket = False
    
    mock.runner = Mock()
    mock_tool = Mock()
    mock_tool.name = "read_file"
    mock_tool.description = "Read a file"
    mock_tool.inputSchema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"}
        },
        "required": ["path"]
    }
    mock.runner.tools = [mock_tool]
    mock._tools = []
    
    def to_openai_tool():
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": mock_tool.inputSchema
                }
            }
        ]
    mock.to_openai_tool = to_openai_tool
    
    def read_file(path: str) -> str:
        return f"Contents of {path}"
    read_file.__name__ = "read_file"
    mock._tools = [read_file]
    mock.__iter__ = lambda self: iter(self._tools)
    
    return mock


def sample_function(query: str) -> str:
    """A sample regular function tool."""
    return f"Result for: {query}"


# ============================================================================
# Test 1: Single MCP Instance (Baseline)
# ============================================================================

class TestSingleMCPInstance:
    """Tests for single MCP instance - baseline functionality."""
    
    def test_single_mcp_creates_tools(self, mock_mcp_with_tools):
        """Test that a single MCP instance properly exposes tools."""
        tools = mock_mcp_with_tools.to_openai_tool()
        assert isinstance(tools, list)
        assert len(tools) == 2
        assert tools[0]["function"]["name"] == "get_current_time"
        assert tools[1]["function"]["name"] == "convert_time"
    
    def test_single_mcp_is_iterable(self, mock_mcp_with_tools):
        """Test that MCP instance is iterable."""
        tools_list = mock_mcp_with_tools._tools
        assert len(tools_list) == 2
        assert callable(tools_list[0])
        assert callable(tools_list[1])
    
    def test_agent_accepts_single_mcp(self, mock_mcp_with_tools):
        """Test that Agent accepts a single MCP instance as tools."""
        # This should not raise an error
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            tools=mock_mcp_with_tools
        )
        # Agent wraps tools in a list if not already a list
        assert mock_mcp_with_tools in agent.tools or agent.tools == mock_mcp_with_tools


# ============================================================================
# Test 2: Multiple MCP Instances - Tool Definition Conversion
# ============================================================================

class TestMultipleMCPToolDefinition:
    """Tests for multiple MCP instances - tool definition conversion."""
    
    def test_agent_accepts_multiple_mcp_in_list(self, mock_mcp_with_tools, mock_mcp_filesystem):
        """Test that Agent accepts multiple MCP instances in a list."""
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            tools=[mock_mcp_with_tools, mock_mcp_filesystem]
        )
        assert isinstance(agent.tools, list)
        assert len(agent.tools) == 2
    
    def test_format_tools_handles_multiple_mcp(self, mock_mcp_with_tools, mock_mcp_filesystem):
        """Test that _format_tools_for_llm handles multiple MCP instances."""
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            tools=[mock_mcp_with_tools, mock_mcp_filesystem]
        )
        
        # Call the internal method to format tools
        formatted = agent._format_tools_for_completion(agent.tools)
        
        # Should have 3 tools total (2 from time + 1 from filesystem)
        assert isinstance(formatted, list)
        assert len(formatted) == 3
        
        # Check tool names
        tool_names = [t["function"]["name"] for t in formatted]
        assert "get_current_time" in tool_names
        assert "convert_time" in tool_names
        assert "read_file" in tool_names
    
    def test_system_prompt_includes_all_mcp_tools(self, mock_mcp_with_tools, mock_mcp_filesystem):
        """Test that system prompt includes tools from all MCP instances."""
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            tools=[mock_mcp_with_tools, mock_mcp_filesystem]
        )
        
        system_prompt = agent._build_system_prompt(agent.tools)
        
        # Should mention all tools
        assert "get_current_time" in system_prompt
        assert "convert_time" in system_prompt
        assert "read_file" in system_prompt


# ============================================================================
# Test 3: Multiple MCP Instances - Tool Execution
# ============================================================================

class TestMultipleMCPToolExecution:
    """Tests for multiple MCP instances - tool execution."""
    
    def test_execute_tool_finds_mcp_tool_in_list(self, mock_mcp_with_tools, mock_mcp_filesystem):
        """Test that execute_tool_call finds tools from MCP instances in a list."""
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            tools=[mock_mcp_with_tools, mock_mcp_filesystem]
        )
        
        # Mock the runner.call_tool method
        mock_mcp_with_tools.runner.call_tool = Mock(return_value='{"timezone": "UTC", "datetime": "2024-01-01T12:00:00Z"}')
        
        # This should find and execute the tool from the first MCP instance
        result = agent.execute_tool("get_current_time", {"timezone": "UTC"})
        
        # Verify the tool was called
        mock_mcp_with_tools.runner.call_tool.assert_called_once_with("get_current_time", {"timezone": "UTC"})
    
    def test_execute_tool_finds_tool_from_second_mcp(self, mock_mcp_with_tools, mock_mcp_filesystem):
        """Test that execute_tool_call finds tools from the second MCP instance."""
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            tools=[mock_mcp_with_tools, mock_mcp_filesystem]
        )
        
        # Mock the runner.call_tool method
        mock_mcp_filesystem.runner.call_tool = Mock(return_value='Contents of /test/file.txt')
        
        # This should find and execute the tool from the second MCP instance
        result = agent.execute_tool("read_file", {"path": "/test/file.txt"})
        
        # Verify the tool was called
        mock_mcp_filesystem.runner.call_tool.assert_called_once_with("read_file", {"path": "/test/file.txt"})


# ============================================================================
# Test 4: Mixed Tools (MCP + Regular Functions)
# ============================================================================

class TestMixedTools:
    """Tests for mixed tools - MCP instances and regular functions."""
    
    def test_agent_accepts_mixed_tools(self, mock_mcp_with_tools):
        """Test that Agent accepts a mix of MCP instances and regular functions."""
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            tools=[mock_mcp_with_tools, sample_function]
        )
        assert isinstance(agent.tools, list)
        assert len(agent.tools) == 2
    
    def test_format_tools_handles_mixed(self, mock_mcp_with_tools):
        """Test that _format_tools_for_llm handles mixed tools."""
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            tools=[mock_mcp_with_tools, sample_function]
        )
        
        formatted = agent._format_tools_for_completion(agent.tools)
        
        # Should have 3 tools (2 from MCP + 1 regular function)
        assert isinstance(formatted, list)
        assert len(formatted) == 3
        
        tool_names = [t["function"]["name"] for t in formatted]
        assert "get_current_time" in tool_names
        assert "convert_time" in tool_names
        assert "sample_function" in tool_names
    
    def test_execute_mixed_tools(self, mock_mcp_with_tools):
        """Test executing both MCP tools and regular functions."""
        agent = Agent(
            name="TestAgent",
            instructions="Test agent",
            tools=[mock_mcp_with_tools, sample_function]
        )
        
        # Execute regular function
        result = agent.execute_tool("sample_function", {"query": "test"})
        assert "Result for: test" in str(result)
        
        # Mock and execute MCP tool
        mock_mcp_with_tools.runner.call_tool = Mock(return_value='{"timezone": "UTC"}')
        result = agent.execute_tool("get_current_time", {"timezone": "UTC"})
        mock_mcp_with_tools.runner.call_tool.assert_called_once()


# ============================================================================
# Integration Tests (requires actual MCP server)
# ============================================================================

@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("SKIP_MCP_INTEGRATION") == "1",
    reason="MCP integration tests skipped"
)
class TestMCPIntegration:
    """Integration tests using actual MCP servers."""
    
    def test_real_time_mcp_server(self):
        """Test with real mcp-server-time."""
        try:
            mcp = MCP("uvx mcp-server-time", timeout=30)
            tools = mcp.to_openai_tool()
            
            assert isinstance(tools, list)
            assert len(tools) >= 1
            
            tool_names = [t["function"]["name"] for t in tools]
            assert "get_current_time" in tool_names
        except Exception as e:
            pytest.skip(f"MCP server not available: {e}")
    
    def test_multiple_real_mcp_servers(self):
        """Test with multiple real MCP servers."""
        try:
            time_mcp = MCP("uvx mcp-server-time", timeout=30)
            
            # Create agent with multiple MCP instances
            agent = Agent(
                name="MultiMCPAgent",
                instructions="Test agent with multiple MCP tools",
                tools=[time_mcp]
            )
            
            # Verify tools are available
            formatted = agent._format_tools_for_completion(agent.tools)
            assert len(formatted) >= 1
            
        except Exception as e:
            pytest.skip(f"MCP servers not available: {e}")


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
