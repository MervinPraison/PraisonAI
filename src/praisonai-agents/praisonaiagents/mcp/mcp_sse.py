"""
SSE (Server-Sent Events) client implementation for MCP (Model Context Protocol).
This module provides the necessary classes and functions to connect to an MCP server
over SSE transport.
"""

import asyncio
import logging
import threading
import inspect
import json
from typing import List, Dict, Any, Optional, Callable, Iterable

from mcp import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger("mcp-sse")

# Global event loop for async operations
_event_loop = None

def get_event_loop():
    """Get or create a global event loop."""
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_event_loop)
    return _event_loop


class SSEMCPTool:
    """A wrapper for an MCP tool that can be used with praisonaiagents."""
    
    def __init__(self, name: str, description: str, session: ClientSession, input_schema: Optional[Dict[str, Any]] = None, timeout: int = 60):
        self.name = name
        self.__name__ = name  # Required for Agent to recognize it as a tool
        self.__qualname__ = name  # Required for Agent to recognize it as a tool
        self.__doc__ = description  # Required for Agent to recognize it as a tool
        self.description = description
        self.session = session
        self.input_schema = input_schema or {}
        self.timeout = timeout
        
        # Create a signature based on input schema
        params = []
        if input_schema and 'properties' in input_schema:
            for param_name in input_schema['properties']:
                params.append(
                    inspect.Parameter(
                        name=param_name,
                        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        default=inspect.Parameter.empty if param_name in input_schema.get('required', []) else None,
                        annotation=str  # Default to string
                    )
                )
        
        self.__signature__ = inspect.Signature(params)
        
    def __call__(self, **kwargs):
        """Synchronous wrapper for the async call."""
        logger.debug(f"Tool {self.name} called with args: {kwargs}")
        
        # Use the global event loop
        loop = get_event_loop()
        
        # Run the async call in the event loop
        future = asyncio.run_coroutine_threadsafe(self._async_call(**kwargs), loop)
        try:
            # Wait for the result with a timeout
            return future.result(timeout=self.timeout)
        except Exception as e:
            logger.error(f"Error calling tool {self.name}: {e}")
            return f"Error: {str(e)}"
    
    async def _async_call(self, **kwargs):
        """Call the tool with the provided arguments."""
        logger.debug(f"Async calling tool {self.name} with args: {kwargs}")
        try:
            result = await self.session.call_tool(self.name, kwargs)
            
            # Extract text from result
            if hasattr(result, 'content') and result.content:
                if hasattr(result.content[0], 'text'):
                    return result.content[0].text
                return str(result.content[0])
            return str(result)
        except Exception as e:
            logger.error(f"Error in _async_call for {self.name}: {e}")
            raise
    
    def to_openai_tool(self):
        """Convert the tool to OpenAI format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema
            }
        }


class SSEMCPClient:
    """A client for connecting to an MCP server over SSE."""
    
    def __init__(self, server_url: str, debug: bool = False, timeout: int = 60):
        """
        Initialize an SSE MCP client.
        
        Args:
            server_url: The URL of the SSE MCP server
            debug: Whether to enable debug logging
            timeout: Timeout in seconds for operations (default: 60)
        """
        self.server_url = server_url
        self.debug = debug
        self.timeout = timeout
        self.session = None
        self.tools = []
        
        # Set up logging
        if debug:
            logger.setLevel(logging.DEBUG)
        else:
            # Set to WARNING by default to hide INFO messages
            logger.setLevel(logging.WARNING)
        
        self._initialize()
        
    def _initialize(self):
        """Initialize the connection and tools."""
        # Use the global event loop
        loop = get_event_loop()
        
        # Start a background thread to run the event loop
        def run_event_loop():
            asyncio.set_event_loop(loop)
            loop.run_forever()
        
        self.loop_thread = threading.Thread(target=run_event_loop, daemon=True)
        self.loop_thread.start()
        
        # Run the initialization in the event loop
        future = asyncio.run_coroutine_threadsafe(self._async_initialize(), loop)
        self.tools = future.result(timeout=self.timeout)
    
    async def _async_initialize(self):
        """Asynchronously initialize the connection and tools."""
        logger.debug(f"Connecting to MCP server at {self.server_url}")
        
        # Create SSE client
        self._streams_context = sse_client(url=self.server_url)
        streams = await self._streams_context.__aenter__()
        
        self._session_context = ClientSession(*streams)
        self.session = await self._session_context.__aenter__()
        
        # Initialize
        await self.session.initialize()
        
        # List available tools
        logger.debug("Listing tools...")
        response = await self.session.list_tools()
        tools_data = response.tools
        logger.debug(f"Found {len(tools_data)} tools: {[tool.name for tool in tools_data]}")
        
        # Create tool wrappers
        tools = []
        for tool in tools_data:
            input_schema = tool.inputSchema if hasattr(tool, 'inputSchema') else None
            wrapper = SSEMCPTool(
                name=tool.name,
                description=tool.description if hasattr(tool, 'description') else f"Call the {tool.name} tool",
                session=self.session,
                input_schema=input_schema,
                timeout=self.timeout
            )
            tools.append(wrapper)
            
        return tools
    
    def __iter__(self):
        """Return an iterator over the tools."""
        return iter(self.tools)
    
    def to_openai_tools(self):
        """Convert all tools to OpenAI format."""
        return [tool.to_openai_tool() for tool in self.tools] 