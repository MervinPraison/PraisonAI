"""
Integration tests for Sequential Thinking MCP server.

These tests verify end-to-end functionality with the Sequential Thinking
MCP server (@modelcontextprotocol/server-sequential-thinking).

Note: These tests require the MCP server to be available via npx.
They are marked as integration tests and can be skipped in CI.
"""

import pytest
import os
import sys

# Skip entire module if MCP package is not installed
try:
    from praisonaiagents.mcp import MCP
    from praisonaiagents import Agent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


@pytest.fixture
def sequential_thinking_mcp():
    """Create a Sequential Thinking MCP server instance."""
    if not MCP_AVAILABLE:
        pytest.skip("MCP package not installed")
    
    try:
        mcp = MCP("npx -y @modelcontextprotocol/server-sequential-thinking", timeout=60)
        yield mcp
        mcp.shutdown()
    except Exception as e:
        pytest.skip(f"Sequential Thinking MCP server not available: {e}")


@pytest.mark.integration
@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP package not installed")
class TestSequentialThinkingMCP:
    """Integration tests for Sequential Thinking MCP server."""
    
    def test_mcp_initializes(self, sequential_thinking_mcp):
        """Test that MCP initializes successfully."""
        assert sequential_thinking_mcp is not None
    
    def test_mcp_has_tools(self, sequential_thinking_mcp):
        """Test that MCP has tools available."""
        tools = sequential_thinking_mcp.get_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
    
    def test_mcp_tools_are_callable(self, sequential_thinking_mcp):
        """Test that MCP tools are callable."""
        tools = sequential_thinking_mcp.get_tools()
        for tool in tools:
            assert callable(tool)
    
    def test_mcp_to_openai_tool(self, sequential_thinking_mcp):
        """Test conversion to OpenAI tool format."""
        openai_tools = sequential_thinking_mcp.to_openai_tool()
        assert isinstance(openai_tools, list)
        assert len(openai_tools) > 0
        
        for tool in openai_tools:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
    
    def test_mcp_iterable(self, sequential_thinking_mcp):
        """Test that MCP is iterable."""
        tools = list(sequential_thinking_mcp)
        assert len(tools) > 0


@pytest.mark.integration
@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP package not installed")
class TestSequentialThinkingWithAgent:
    """Integration tests for Sequential Thinking MCP with Agent."""
    
    @pytest.fixture
    def agent_with_sequential_thinking(self):
        """Create an Agent with Sequential Thinking MCP tools."""
        try:
            mcp = MCP("npx -y @modelcontextprotocol/server-sequential-thinking", timeout=60)
            agent = Agent(
                name="SequentialThinkingAgent",
                instructions="You are a helpful assistant that breaks down complex problems step by step.",
                tools=mcp
            )
            yield agent, mcp
            mcp.shutdown()
        except Exception as e:
            pytest.skip(f"Could not create agent with MCP: {e}")
    
    def test_agent_accepts_mcp_tools(self, agent_with_sequential_thinking):
        """Test that Agent accepts MCP tools."""
        agent, mcp = agent_with_sequential_thinking
        assert agent is not None
        assert agent.tools is not None
    
    def test_agent_formats_mcp_tools(self, agent_with_sequential_thinking):
        """Test that Agent can format MCP tools for LLM."""
        agent, mcp = agent_with_sequential_thinking
        
        # Get formatted tools
        formatted = agent._format_tools_for_completion(agent.tools)
        
        assert isinstance(formatted, list)
        assert len(formatted) > 0


@pytest.mark.integration
@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP package not installed")
@pytest.mark.skipif(
    os.environ.get("SKIP_LLM_TESTS") == "1",
    reason="LLM tests skipped"
)
class TestSequentialThinkingEndToEnd:
    """End-to-end tests with actual LLM calls."""
    
    @pytest.fixture
    def agent_with_llm(self):
        """Create an Agent with LLM and Sequential Thinking MCP."""
        try:
            mcp = MCP("npx -y @modelcontextprotocol/server-sequential-thinking", timeout=60)
            agent = Agent(
                name="SequentialThinkingAgent",
                instructions="You are a helpful assistant that breaks down complex problems step by step. Use the sequential thinking tool when asked to break down a problem.",
                llm="openai/gpt-4o-mini",
                tools=mcp
            )
            yield agent, mcp
            mcp.shutdown()
        except Exception as e:
            pytest.skip(f"Could not create agent: {e}")
    
    def test_agent_can_use_sequential_thinking(self, agent_with_llm):
        """Test that agent can use sequential thinking tool."""
        agent, mcp = agent_with_llm
        
        # This test requires an API key and will make actual LLM calls
        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        response = agent.chat("Break down the process of making a cup of tea into steps")
        
        assert response is not None
        assert len(response) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
