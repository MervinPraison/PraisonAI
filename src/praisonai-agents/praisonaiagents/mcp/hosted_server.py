"""
Hosted MCP Server implementation for PraisonAI Agents.

This module provides a base class for creating hosted MCP servers
that can handle requests and integrate with the MCP protocol.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from abc import ABC, abstractmethod
import json

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.server import Server
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.routing import Mount, Route
    from mcp.server.sse import SseServerTransport
    import uvicorn
except ImportError:
    raise ImportError(
        "MCP server dependencies not installed. "
        "Please install with: pip install praisonaiagents[mcp]"
    )

logger = logging.getLogger(__name__)


class HostedMCPServer(ABC):
    """
    Base class for creating hosted MCP servers.
    
    This class provides a foundation for building MCP servers that can:
    - Handle incoming requests
    - Define custom tools
    - Support SSE transport
    - Be extended with custom functionality like latency tracking
    """
    
    def __init__(self, name: str = "hosted-mcp-server", host: str = "localhost", port: int = 8080):
        """
        Initialize the hosted MCP server.
        
        Args:
            name: Server name for identification
            host: Host to bind to (default: localhost)
            port: Port to listen on (default: 8080)
        """
        self.name = name
        self.host = host
        self.port = port
        self.mcp = FastMCP(name)
        self._tools: Dict[str, Callable] = {}
        self._server: Optional[Server] = None
        self._app: Optional[Starlette] = None
        
    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle incoming MCP requests.
        
        This method can be overridden in subclasses to add custom request handling,
        such as latency tracking, authentication, or request modification.
        
        Args:
            request_data: The incoming request data
            
        Returns:
            Response data
        """
        # Default implementation - can be overridden
        method = request_data.get('method', '')
        request_id = request_data.get('id', 'unknown')
        
        logger.debug(f"Handling request {request_id}: {method}")
        
        # Basic response structure
        response = {
            'id': request_id,
            'jsonrpc': '2.0',
            'result': {}
        }
        
        return response
    
    def add_tool(self, func: Callable, name: Optional[str] = None, description: Optional[str] = None):
        """
        Add a tool to the MCP server.
        
        Args:
            func: The function to expose as a tool
            name: Optional name for the tool (defaults to function name)
            description: Optional description for the tool
        """
        tool_name = name or func.__name__
        
        # Register with FastMCP
        if asyncio.iscoroutinefunction(func):
            # Already async
            self.mcp.tool(name=tool_name)(func)
        else:
            # Wrap sync function in async
            async def async_wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            async_wrapper.__name__ = func.__name__
            async_wrapper.__doc__ = description or func.__doc__
            self.mcp.tool(name=tool_name)(async_wrapper)
        
        self._tools[tool_name] = func
        logger.info(f"Added tool: {tool_name}")
    
    def create_app(self, debug: bool = False) -> Starlette:
        """
        Create a Starlette application for serving the MCP server.
        
        Args:
            debug: Enable debug mode
            
        Returns:
            Starlette application instance
        """
        if not self._server:
            self._server = self.mcp._mcp_server
        
        sse = SseServerTransport("/messages/")
        
        async def handle_sse(request: Request) -> None:
            logger.debug(f"SSE connection from {request.client}")
            async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,
            ) as (read_stream, write_stream):
                await self._server.run(
                    read_stream,
                    write_stream,
                    self._server.create_initialization_options(),
                )
        
        self._app = Starlette(
            debug=debug,
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )
        
        return self._app
    
    def start(self, debug: bool = False, **uvicorn_kwargs):
        """
        Start the MCP server.
        
        Args:
            debug: Enable debug mode
            **uvicorn_kwargs: Additional arguments to pass to uvicorn
        """
        app = self.create_app(debug=debug)
        
        print(f"Starting {self.name} MCP server on {self.host}:{self.port}")
        print(f"Available tools: {', '.join(self._tools.keys())}")
        print(f"SSE endpoint: http://{self.host}:{self.port}/sse")
        
        uvicorn.run(app, host=self.host, port=self.port, **uvicorn_kwargs)
    
    async def start_async(self, debug: bool = False):
        """
        Start the MCP server asynchronously.
        
        Args:
            debug: Enable debug mode
        """
        app = self.create_app(debug=debug)
        
        config = uvicorn.Config(app, host=self.host, port=self.port)
        server = uvicorn.Server(config)
        
        print(f"Starting {self.name} MCP server on {self.host}:{self.port}")
        print(f"Available tools: {', '.join(self._tools.keys())}")
        
        await server.serve()
    
    def get_tools(self) -> List[str]:
        """Get list of available tool names."""
        return list(self._tools.keys())
    
    def get_endpoint(self) -> str:
        """Get the SSE endpoint URL."""
        return f"http://{self.host}:{self.port}/sse"