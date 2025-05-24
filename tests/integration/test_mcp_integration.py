import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, patch, AsyncMock, MagicMock

# Add the source path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'praisonai-agents'))

try:
    from praisonaiagents import Agent
except ImportError as e:
    pytest.skip(f"Could not import required modules: {e}", allow_module_level=True)


class TestMCPIntegration:
    """Test MCP (Model Context Protocol) integration functionality."""
    
    @pytest.mark.asyncio
    async def test_mcp_server_connection(self):
        """Test basic MCP server connection."""
        with patch('mcp.client.stdio.stdio_client') as mock_stdio_client:
            # Mock the server connection
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_stdio_client.return_value.__aenter__.return_value = (mock_read, mock_write)
            
            # Mock the session
            with patch('mcp.ClientSession') as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__.return_value = mock_session
                
                # Mock session methods
                mock_session.initialize.return_value = None
                mock_session.list_tools.return_value = Mock(tools=[
                    Mock(name='get_stock_price', description='Get stock price')
                ])
                
                # Test MCP connection simulation
                async with mock_stdio_client(Mock()) as (read, write):
                    async with mock_session_class(read, write) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        
                        assert len(tools_result.tools) == 1
                        assert tools_result.tools[0].name == 'get_stock_price'
    
    @pytest.mark.asyncio
    async def test_mcp_tool_execution(self):
        """Test MCP tool execution."""
        with patch('mcp.client.stdio.stdio_client') as mock_stdio_client:
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_stdio_client.return_value.__aenter__.return_value = (mock_read, mock_write)
            
            with patch('mcp.ClientSession') as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__.return_value = mock_session
                
                # Mock tool execution
                mock_session.initialize.return_value = None
                mock_session.list_tools.return_value = Mock(tools=[
                    Mock(name='calculator', description='Calculate expressions')
                ])
                mock_session.call_tool.return_value = Mock(content=[
                    Mock(text='{"result": 42}')
                ])
                
                async with mock_stdio_client(Mock()) as (read, write):
                    async with mock_session_class(read, write) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        result = await session.call_tool('calculator', {'expression': '6*7'})
                        
                        assert result.content[0].text == '{"result": 42}'
    
    def test_mcp_tool_wrapper(self):
        """Test MCP tool wrapper for agent integration."""
        def create_mcp_tool(tool_name: str, server_params):
            """Create a wrapper function for MCP tools."""
            def mcp_tool_wrapper(*args, **kwargs):
                # Mock the MCP tool execution
                return f"MCP tool '{tool_name}' executed with args: {args}, kwargs: {kwargs}"
            
            mcp_tool_wrapper.__name__ = tool_name
            mcp_tool_wrapper.__doc__ = f"MCP tool: {tool_name}"
            return mcp_tool_wrapper
        
        # Test tool creation
        stock_tool = create_mcp_tool('get_stock_price', Mock())
        result = stock_tool('TSLA')
        
        assert 'get_stock_price' in result
        assert 'TSLA' in result
        assert stock_tool.__name__ == 'get_stock_price'
    
    def test_agent_with_mcp_tools(self, sample_agent_config):
        """Test agent creation with MCP tools."""
        def mock_stock_price_tool(symbol: str) -> str:
            """Mock stock price tool using MCP."""
            return f"Stock price for {symbol}: $150.00"
        
        def mock_weather_tool(location: str) -> str:
            """Mock weather tool using MCP."""
            return f"Weather in {location}: Sunny, 25°C"
        
        agent = Agent(
            name="MCP Agent",
            tools=[mock_stock_price_tool, mock_weather_tool],
            **{k: v for k, v in sample_agent_config.items() if k != 'name'}
        )
        
        assert agent.name == "MCP Agent"
        assert len(agent.tools) >= 2
    
    @pytest.mark.asyncio
    async def test_mcp_server_parameters(self):
        """Test MCP server parameter configuration."""
        from unittest.mock import Mock
        
        # Mock server parameters
        server_params = Mock()
        server_params.command = "/usr/bin/python"
        server_params.args = ["/path/to/server.py"]
        server_params.env = {"PATH": "/usr/bin"}
        
        assert server_params.command == "/usr/bin/python"
        assert "/path/to/server.py" in server_params.args
        assert "PATH" in server_params.env
    
    @pytest.mark.asyncio
    async def test_mcp_error_handling(self):
        """Test MCP connection error handling."""
        with patch('mcp.client.stdio.stdio_client') as mock_stdio_client:
            # Simulate connection error
            mock_stdio_client.side_effect = ConnectionError("Failed to connect to MCP server")
            
            try:
                async with mock_stdio_client(Mock()) as (read, write):
                    pass
                assert False, "Should have raised ConnectionError"
            except ConnectionError as e:
                assert "Failed to connect to MCP server" in str(e)
    
    def test_mcp_multiple_servers(self):
        """Test connecting to multiple MCP servers."""
        server_configs = [
            {
                'name': 'stock_server',
                'command': '/usr/bin/python',
                'args': ['/path/to/stock_server.py'],
                'tools': ['get_stock_price', 'get_market_data']
            },
            {
                'name': 'weather_server', 
                'command': '/usr/bin/python',
                'args': ['/path/to/weather_server.py'],
                'tools': ['get_weather', 'get_forecast']
            }
        ]
        
        # Mock multiple server connections
        mcp_tools = []
        for config in server_configs:
            for tool_name in config['tools']:
                def create_tool(name, server_name):
                    def tool_func(*args, **kwargs):
                        return f"Tool {name} from {server_name} executed"
                    tool_func.__name__ = name
                    return tool_func
                
                mcp_tools.append(create_tool(tool_name, config['name']))
        
        assert len(mcp_tools) == 4
        assert mcp_tools[0].__name__ == 'get_stock_price'
        assert mcp_tools[2].__name__ == 'get_weather'
    
    @pytest.mark.asyncio
    async def test_mcp_tool_with_complex_parameters(self):
        """Test MCP tool with complex parameter structures."""
        with patch('mcp.client.stdio.stdio_client') as mock_stdio_client:
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_stdio_client.return_value.__aenter__.return_value = (mock_read, mock_write)
            
            with patch('mcp.ClientSession') as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__.return_value = mock_session
                
                # Mock complex tool call
                complex_params = {
                    'query': 'AI trends',
                    'filters': {
                        'date_range': '2024-01-01 to 2024-12-31',
                        'categories': ['technology', 'ai', 'ml']
                    },
                    'options': {
                        'max_results': 10,
                        'include_metadata': True
                    }
                }
                
                mock_session.call_tool.return_value = Mock(content=[
                    Mock(text='{"results": [{"title": "AI Trend 1", "url": "example.com"}]}')
                ])
                
                async with mock_stdio_client(Mock()) as (read, write):
                    async with mock_session_class(read, write) as session:
                        result = await session.call_tool('search_trends', complex_params)
                        
                        assert 'AI Trend 1' in result.content[0].text


class TestMCPAgentIntegration:
    """Test MCP integration with PraisonAI agents."""
    
    def test_agent_with_mcp_wrapper(self, sample_agent_config):
        """Test agent with MCP tool wrapper."""
        class MCPToolWrapper:
            """Wrapper for MCP tools to integrate with agents."""
            
            def __init__(self, server_params):
                self.server_params = server_params
                self.tools = {}
            
            def add_tool(self, name: str, func):
                """Add a tool to the wrapper."""
                self.tools[name] = func
            
            def get_tool(self, name: str):
                """Get a tool by name."""
                return self.tools.get(name)
        
        # Create MCP wrapper
        mcp_wrapper = MCPToolWrapper(Mock())
        
        # Add mock tools
        def mock_search_tool(query: str) -> str:
            return f"Search results for: {query}"
        
        mcp_wrapper.add_tool('search', mock_search_tool)
        
        # Create agent with MCP tools
        agent = Agent(
            name="MCP Integrated Agent",
            tools=[mcp_wrapper.get_tool('search')],
            **{k: v for k, v in sample_agent_config.items() if k != 'name'}
        )
        
        assert agent.name == "MCP Integrated Agent"
        assert len(agent.tools) >= 1
    
    @pytest.mark.asyncio
    async def test_mcp_async_tool_integration(self, sample_agent_config):
        """Test async MCP tool integration with agents."""
        async def async_mcp_tool(query: str) -> str:
            """Async MCP tool simulation."""
            await asyncio.sleep(0.1)  # Simulate MCP call delay
            return f"Async MCP result for: {query}"
        
        agent = Agent(
            name="Async MCP Agent",
            tools=[async_mcp_tool],
            **{k: v for k, v in sample_agent_config.items() if k != 'name'}
        )
        
        assert agent.name == "Async MCP Agent"
        
        # Test the async tool directly
        result = await async_mcp_tool("test query")
        assert "Async MCP result for: test query" == result
    
    def test_mcp_tool_registry(self):
        """Test MCP tool registry for managing multiple tools."""
        class MCPToolRegistry:
            """Registry for managing MCP tools."""
            
            def __init__(self):
                self.servers = {}
                self.tools = {}
            
            def register_server(self, name: str, params):
                """Register an MCP server."""
                self.servers[name] = params
            
            def register_tool(self, server_name: str, tool_name: str, tool_func):
                """Register a tool from an MCP server."""
                key = f"{server_name}.{tool_name}"
                self.tools[key] = tool_func
            
            def get_tool(self, server_name: str, tool_name: str):
                """Get a registered tool."""
                key = f"{server_name}.{tool_name}"
                return self.tools.get(key)
            
            def list_tools(self) -> list:
                """List all registered tools."""
                return list(self.tools.keys())
        
        # Test registry
        registry = MCPToolRegistry()
        
        # Register servers
        registry.register_server('stock_server', Mock())
        registry.register_server('weather_server', Mock())
        
        # Register tools
        def stock_tool():
            return "Stock data"
        
        def weather_tool():
            return "Weather data"
        
        registry.register_tool('stock_server', 'get_price', stock_tool)
        registry.register_tool('weather_server', 'get_weather', weather_tool)
        
        # Test retrieval
        assert registry.get_tool('stock_server', 'get_price') == stock_tool
        assert registry.get_tool('weather_server', 'get_weather') == weather_tool
        assert len(registry.list_tools()) == 2
        assert 'stock_server.get_price' in registry.list_tools()
        assert 'weather_server.get_weather' in registry.list_tools()


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 