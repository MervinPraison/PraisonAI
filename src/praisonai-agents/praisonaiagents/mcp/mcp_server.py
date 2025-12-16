"""MCP Server wrapper for exposing PraisonAI tools as MCP servers.

This module provides a simple way to expose Python functions as MCP tools
that can be consumed by any MCP client (Claude Desktop, Cursor, etc.).

Usage:
    from praisonaiagents.mcp import ToolsMCPServer
    
    def search(query: str) -> str:
        '''Search the web.'''
        return f"Results for {query}"
    
    server = ToolsMCPServer(name="my-tools")
    server.register_tool(search)
    server.run()  # Starts MCP server (stdio by default)
"""

import asyncio
import inspect
import logging
from typing import Any, Callable, Dict, List, Optional

from .mcp_utils import function_to_mcp_schema

logger = logging.getLogger(__name__)


class ToolsMCPServer:
    """MCP Server that exposes Python functions as MCP tools.
    
    This class wraps Python functions and exposes them as MCP tools
    using the FastMCP library. It supports both sync and async functions.
    
    Example:
        server = ToolsMCPServer(name="my-tools")
        
        def search(query: str) -> str:
            '''Search the web.'''
            return f"Results for {query}"
        
        server.register_tool(search)
        server.run()  # Starts stdio server
    """
    
    def __init__(
        self,
        name: str = "praisonai-tools",
        tools: Optional[List[Callable]] = None,
        debug: bool = False
    ):
        """Initialize the MCP server.
        
        Args:
            name: Name of the MCP server
            tools: Optional list of tools to register on init
            debug: Enable debug logging
        """
        self.name = name
        self.tools: List[Callable] = []
        self._tool_map: Dict[str, Callable] = {}
        self._fastmcp = None
        self._debug = debug
        
        if debug:
            logger.setLevel(logging.DEBUG)
        
        # Register initial tools if provided
        if tools:
            self.register_tools(tools)
    
    def register_tool(self, func: Callable) -> None:
        """Register a single tool function.
        
        Args:
            func: The function to register as an MCP tool
        """
        if not callable(func):
            raise TypeError(f"Expected callable, got {type(func)}")
        
        self.tools.append(func)
        tool_name = getattr(func, '__mcp_name__', None) or func.__name__
        self._tool_map[tool_name] = func
        
        logger.debug(f"Registered tool: {tool_name}")
    
    def register_tools(self, funcs: List[Callable]) -> None:
        """Register multiple tool functions.
        
        Args:
            funcs: List of functions to register as MCP tools
        """
        for func in funcs:
            self.register_tool(func)
    
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get MCP schemas for all registered tools.
        
        Returns:
            List of MCP tool schema dictionaries
        """
        return [function_to_mcp_schema(tool) for tool in self.tools]
    
    def get_tool_names(self) -> List[str]:
        """Get names of all registered tools.
        
        Returns:
            List of tool names
        """
        return list(self._tool_map.keys())
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a registered tool synchronously.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool
        
        Returns:
            Result from the tool execution
        
        Raises:
            ValueError: If tool is not found
        """
        if tool_name not in self._tool_map:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        func = self._tool_map[tool_name]
        
        # Handle async functions
        if asyncio.iscoroutinefunction(func):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(func(**arguments))
            finally:
                loop.close()
        
        return func(**arguments)
    
    async def execute_tool_async(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a registered tool asynchronously.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool
        
        Returns:
            Result from the tool execution
        
        Raises:
            ValueError: If tool is not found
        """
        if tool_name not in self._tool_map:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        func = self._tool_map[tool_name]
        
        if asyncio.iscoroutinefunction(func):
            return await func(**arguments)
        
        # Run sync function in executor
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(**arguments))
    
    def get_fastmcp(self):
        """Get or create FastMCP instance with registered tools.
        
        Returns:
            FastMCP instance with all tools registered
        """
        if self._fastmcp is None:
            self._fastmcp = self._create_fastmcp()
        return self._fastmcp
    
    def _create_fastmcp(self):
        """Create FastMCP instance and register all tools.
        
        Returns:
            Configured FastMCP instance
        """
        try:
            from mcp.server.fastmcp import FastMCP
        except ImportError:
            raise ImportError(
                "FastMCP not available. Install with: pip install mcp"
            )
        
        mcp = FastMCP(self.name)
        
        # Register each tool with FastMCP
        for func in self.tools:
            self._register_tool_with_fastmcp(mcp, func)
        
        return mcp
    
    def _register_tool_with_fastmcp(self, mcp, func: Callable) -> None:
        """Register a single function with FastMCP.
        
        Args:
            mcp: FastMCP instance
            func: Function to register
        """
        # Get tool metadata
        tool_name = getattr(func, '__mcp_name__', None) or func.__name__
        description = getattr(func, '__mcp_description__', None)
        if description is None:
            docstring = inspect.getdoc(func)
            description = docstring.split('\n')[0] if docstring else tool_name
        
        # Create wrapper that preserves signature
        if asyncio.iscoroutinefunction(func):
            @mcp.tool(name=tool_name, description=description)
            async def tool_wrapper(**kwargs):
                return await func(**kwargs)
        else:
            @mcp.tool(name=tool_name, description=description)
            def tool_wrapper(**kwargs):
                return func(**kwargs)
        
        # Copy signature for proper schema generation
        tool_wrapper.__signature__ = inspect.signature(func)
        tool_wrapper.__annotations__ = getattr(func, '__annotations__', {})
    
    def run(self, transport: str = "stdio") -> None:
        """Run the MCP server.
        
        Args:
            transport: Transport type - "stdio" or "sse"
        """
        if transport == "stdio":
            self.run_stdio()
        elif transport == "sse":
            self.run_sse()
        else:
            raise ValueError(f"Unknown transport: {transport}. Use 'stdio' or 'sse'")
    
    def run_stdio(self) -> None:
        """Run the MCP server using stdio transport."""
        mcp = self.get_fastmcp()
        
        print(f"🚀 Starting MCP server '{self.name}' with stdio transport")
        print(f"🛠️  Available tools: {', '.join(self.get_tool_names())}")
        
        mcp.run()
    
    def run_sse(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """Run the MCP server using SSE transport.
        
        Args:
            host: Host to bind to
            port: Port to listen on
        """
        try:
            import uvicorn
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.requests import Request
            from starlette.routing import Mount, Route
        except ImportError as e:
            raise ImportError(
                f"SSE dependencies not available: {e}. "
                "Install with: pip install uvicorn starlette"
            )
        
        mcp = self.get_fastmcp()
        
        # Set up SSE transport
        sse_path = "/sse"
        messages_path = "/messages/"
        
        sse_transport = SseServerTransport(messages_path)
        
        async def handle_sse(request: Request):
            async with sse_transport.connect_sse(
                request.scope, request.receive, request._send
            ) as (read_stream, write_stream):
                await mcp._mcp_server.run(
                    read_stream,
                    write_stream,
                    mcp._mcp_server.create_initialization_options()
                )
        
        app = Starlette(
            debug=self._debug,
            routes=[
                Route(sse_path, endpoint=handle_sse),
                Mount(messages_path, app=sse_transport.handle_post_message),
            ]
        )
        
        print(f"🚀 Starting MCP server '{self.name}' with SSE transport")
        print(f"📡 SSE endpoint: http://{host}:{port}{sse_path}")
        print(f"🛠️  Available tools: {', '.join(self.get_tool_names())}")
        
        uvicorn.run(app, host=host, port=port)


def launch_tools_mcp_server(
    tools: Optional[List[Callable]] = None,
    tool_names: Optional[List[str]] = None,
    name: str = "praisonai-tools",
    transport: str = "stdio",
    host: str = "0.0.0.0",
    port: int = 8080,
    debug: bool = False
) -> None:
    """Convenience function to launch an MCP server with tools.
    
    Args:
        tools: List of tool functions to expose
        tool_names: List of tool names to load from praisonaiagents.tools
        name: Name of the MCP server
        transport: Transport type - "stdio" or "sse"
        host: Host for SSE transport
        port: Port for SSE transport
        debug: Enable debug logging
    
    Example:
        # With custom tools
        def my_search(query: str) -> str:
            return f"Results for {query}"
        
        launch_tools_mcp_server(tools=[my_search])
        
        # With built-in tools
        launch_tools_mcp_server(tool_names=["tavily_search", "exa_search"])
    """
    server = ToolsMCPServer(name=name, debug=debug)
    
    # Register custom tools
    if tools:
        server.register_tools(tools)
    
    # Load and register tools by name
    if tool_names:
        from praisonaiagents import tools as praison_tools
        
        for tool_name in tool_names:
            if hasattr(praison_tools, tool_name):
                tool_func = getattr(praison_tools, tool_name)
                if callable(tool_func):
                    server.register_tool(tool_func)
                else:
                    logger.warning(f"Tool '{tool_name}' is not callable")
            else:
                logger.warning(f"Tool '{tool_name}' not found in praisonaiagents.tools")
    
    if not server.tools:
        raise ValueError("No tools registered. Provide 'tools' or 'tool_names'.")
    
    # Run the server
    if transport == "stdio":
        server.run_stdio()
    elif transport == "sse":
        server.run_sse(host=host, port=port)
    else:
        raise ValueError(f"Unknown transport: {transport}")
