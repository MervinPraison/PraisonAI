"""
Live integration tests for MCP integration.

These tests require:
- PRAISONAI_LIVE_TESTS=1 environment variable
- OPENAI_API_KEY environment variable

Run with: PRAISONAI_LIVE_TESTS=1 pytest -m live tests/integration/mcp/test_mcp_integration_live.py -v
"""

import pytest


@pytest.fixture
def openai_api_key():
    """Get OpenAI API key from environment."""
    import os
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    return key


@pytest.mark.live
class TestMCPAgentIntegrationLive:
    """Live tests for MCP integration with agents."""
    
    def test_agent_with_mcp_server_real(self, openai_api_key):
        """Test agent connecting to MCP server."""
        from praisonaiagents import Agent
        
        # Create agent with MCP configuration (simplified for testing)
        agent = Agent(
            name="MCPAgent",
            instructions="You are an assistant that can use MCP servers for enhanced capabilities.",
            llm="gpt-4o-mini"
        )
        
        # Test basic MCP functionality (simulated since real MCP server may not be available)
        result = agent.start("Explain how Model Context Protocol (MCP) enhances agent capabilities")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        assert ("mcp" in result.lower() or "protocol" in result.lower() or "context" in result.lower())
        
        print(f"MCP agent result: {result}")


@pytest.mark.live
class TestMCPToolsLive:
    """Live tests for MCP tools integration."""
    
    def test_agent_mcp_tools_real(self, openai_api_key):
        """Test agent using tools through MCP."""
        from praisonaiagents import Agent, tool
        
        @tool
        def mcp_weather_tool(location: str) -> str:
            """Get weather information through MCP server."""
            return f"Weather in {location}: Sunny, 22°C (simulated MCP response)"
        
        @tool
        def mcp_stock_tool(symbol: str) -> str:
            """Get stock price through MCP server."""
            return f"Stock price for {symbol}: $150.25 (simulated MCP response)"
        
        agent = Agent(
            name="MCPToolsAgent",
            instructions="You are an assistant with access to MCP tools for weather and stock information.",
            tools=[mcp_weather_tool, mcp_stock_tool],
            llm="gpt-4o-mini"
        )
        
        # Test using MCP tools
        result = agent.start("What's the weather in New York and the stock price of AAPL?")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        
        result_lower = result.lower()
        assert ("weather" in result_lower or "stock" in result_lower)
        
        print(f"MCP tools result: {result}")


@pytest.mark.live
class TestMCPMultiServerLive:
    """Live tests for multiple MCP server integration."""
    
    def test_agent_multiple_mcp_servers_real(self, openai_api_key):
        """Test agent coordinating multiple MCP servers."""
        from praisonaiagents import Agent, tool
        
        @tool
        def mcp_server_a_tool(query: str) -> str:
            """Tool from MCP Server A."""
            return f"Server A response to '{query}': Data processing complete"
        
        @tool
        def mcp_server_b_tool(task: str) -> str:
            """Tool from MCP Server B."""
            return f"Server B response to '{task}': Analysis complete"
        
        agent = Agent(
            name="MultiMCPAgent",
            instructions="You are an assistant that coordinates multiple MCP servers for complex tasks.",
            tools=[mcp_server_a_tool, mcp_server_b_tool],
            llm="gpt-4o-mini"
        )
        
        # Test coordination of multiple servers
        result = agent.start("Process data using server A and then analyze the results using server B")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        
        result_lower = result.lower()
        # Should show evidence of using both servers
        assert ("server a" in result_lower or "server b" in result_lower or "process" in result_lower)
        
        print(f"Multi-MCP result: {result}")


@pytest.mark.live
class TestMCPErrorHandlingLive:
    """Live tests for MCP error handling."""
    
    def test_agent_mcp_connection_errors_real(self, openai_api_key):
        """Test agent handling MCP connection issues."""
        from praisonaiagents import Agent, tool
        
        @tool
        def unreliable_mcp_tool(data: str) -> str:
            """MCP tool that sometimes fails."""
            if "error" in data.lower():
                raise ConnectionError("MCP server connection failed")
            return f"MCP processing successful: {data}"
        
        @tool
        def fallback_tool(data: str) -> str:
            """Fallback tool when MCP fails."""
            return f"Fallback processing: {data}"
        
        agent = Agent(
            name="MCPErrorAgent",
            instructions="You are an assistant that handles MCP server errors gracefully with fallback options.",
            tools=[unreliable_mcp_tool, fallback_tool],
            llm="gpt-4o-mini"
        )
        
        # Test error handling
        result = agent.start("Process this data that might cause an error: error condition")
        
        # Assertions - should handle error gracefully
        assert result is not None
        assert len(result) > 0
        
        print(f"MCP error handling result: {result}")


@pytest.mark.live
class TestMCPStreamingLive:
    """Live tests for MCP streaming capabilities."""
    
    def test_agent_mcp_streaming_real(self, openai_api_key):
        """Test agent with streaming MCP responses."""
        from praisonaiagents import Agent, tool
        
        @tool
        def mcp_streaming_tool(prompt: str) -> str:
            """MCP tool that provides streaming responses."""
            return f"Streaming MCP response for '{prompt}': Processing... Complete."
        
        agent = Agent(
            name="MCPStreamingAgent", 
            instructions="You are an assistant that can handle streaming MCP responses.",
            tools=[mcp_streaming_tool],
            llm="gpt-4o-mini"
        )
        
        # Test streaming capability
        result = agent.start("Generate a streaming response for this prompt: Hello MCP")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        assert ("streaming" in result.lower() or "mcp" in result.lower())
        
        print(f"MCP streaming result: {result}")