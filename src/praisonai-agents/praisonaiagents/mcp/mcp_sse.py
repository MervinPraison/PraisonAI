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
            for param_name, prop_schema in input_schema['properties'].items():
                # Determine type annotation based on schema
                prop_type = prop_schema.get('type', 'string') if isinstance(prop_schema, dict) else 'string'
                if prop_type == 'string':
                    annotation = str
                elif prop_type == 'integer':
                    annotation = int
                elif prop_type == 'number':
                    annotation = float
                elif prop_type == 'boolean':
                    annotation = bool
                elif prop_type == 'array':
                    annotation = list
                elif prop_type == 'object':
                    annotation = dict
                else:
                    annotation = str  # Default to string for SSE
                
                params.append(
                    inspect.Parameter(
                        name=param_name,
                        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        default=inspect.Parameter.empty if param_name in input_schema.get('required', []) else None,
                        annotation=annotation
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
    
    def _fix_array_schemas(self, schema):
        """
        Fix array schemas by adding missing 'items' attribute required by OpenAI.
        
        This ensures compatibility with OpenAI's function calling format which
        requires array types to specify the type of items they contain.
        
        Args:
            schema: The schema dictionary to fix
            
        Returns:
            dict: The fixed schema
        """
        if not isinstance(schema, dict):
            return schema
            
        # Create a copy to avoid modifying the original
        fixed_schema = schema.copy()
        
        # Fix array types at the current level
        if fixed_schema.get("type") == "array" and "items" not in fixed_schema:
            # Add a default items schema for arrays without it
            fixed_schema["items"] = {"type": "string"}
            
        # Recursively fix nested schemas
        if "properties" in fixed_schema:
            fixed_properties = {}
            for prop_name, prop_schema in fixed_schema["properties"].items():
                fixed_properties[prop_name] = self._fix_array_schemas(prop_schema)
            fixed_schema["properties"] = fixed_properties
            
        # Fix items schema if it exists
        if "items" in fixed_schema:
            fixed_schema["items"] = self._fix_array_schemas(fixed_schema["items"])
            
        return fixed_schema
    
    def to_openai_tool(self):
        """Convert the tool to OpenAI format."""
        # Fix array schemas to include 'items' attribute
        fixed_schema = self._fix_array_schemas(self.input_schema)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": fixed_schema
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