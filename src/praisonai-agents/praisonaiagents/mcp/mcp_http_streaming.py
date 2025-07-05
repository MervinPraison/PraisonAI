"""
HTTP-Streaming client implementation for MCP (Model Context Protocol).
This module provides HTTP chunked streaming transport as an alternative to SSE.
"""

import asyncio
import logging
import threading
import inspect
import json
from typing import List, Dict, Any, Optional, Callable, AsyncIterator
import httpx
from functools import wraps

from mcp import ClientSession
from mcp.client.session import Transport
from mcp.shared.jsonrpc import JSONRPCRequest, JSONRPCResponse, JSONRPCError

logger = logging.getLogger("mcp-http-streaming")

# Global event loop for async operations
_event_loop = None

def get_event_loop():
    """Get or create a global event loop."""
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_event_loop)
    return _event_loop


class HTTPStreamingTransport(Transport):
    """HTTP chunked streaming transport for MCP."""
    
    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None):
        self.url = url
        self.headers = headers or {}
        self.headers['Content-Type'] = 'application/json'
        self.client = httpx.AsyncClient(timeout=60.0)
        self._request_id = 0
        
    def _get_next_id(self) -> int:
        """Generate the next request ID."""
        self._request_id += 1
        return self._request_id
        
    async def send_request(self, request: JSONRPCRequest) -> None:
        """Send a request to the server."""
        data = json.dumps(request.model_dump())
        await self.client.post(self.url, content=data, headers=self.headers)
        
    async def receive_response(self) -> JSONRPCResponse:
        """Receive a response from the server using HTTP streaming."""
        # For HTTP-Streaming, we send a GET request to read the stream
        stream_url = self.url.replace('/stream', '/stream/read') if '/stream' in self.url else f"{self.url}/read"
        
        async with self.client.stream('GET', stream_url, headers=self.headers) as response:
            # Read chunked response
            buffer = b""
            async for chunk in response.aiter_bytes():
                buffer += chunk
                # Try to parse complete JSON messages from buffer
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            return JSONRPCResponse(**data)
                        except json.JSONDecodeError:
                            continue
            
            # Handle remaining data in buffer
            if buffer:
                try:
                    data = json.loads(buffer.decode('utf-8'))
                    return JSONRPCResponse(**data)
                except json.JSONDecodeError:
                    pass
                    
        raise Exception("No valid response received from stream")
        
    async def send_and_receive(self, request_data: dict) -> dict:
        """Send a request and receive a response."""
        # Create request with ID
        request_data['id'] = self._get_next_id()
        request = JSONRPCRequest(**request_data)
        
        # Send request
        await self.send_request(request)
        
        # Receive response
        response = await self.receive_response()
        
        if hasattr(response, 'error') and response.error:
            raise Exception(f"JSON-RPC error: {response.error}")
            
        return response.result if hasattr(response, 'result') else {}
        
    async def close(self) -> None:
        """Close the transport."""
        await self.client.aclose()


class HTTPStreamingMCPTool:
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
    
    def _fix_array_schemas(self, schema):
        """
        Fix array schemas by adding missing 'items' attribute required by OpenAI.
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


class HTTPStreamingMCPClient:
    """A client for connecting to an MCP server over HTTP-Streaming."""
    
    def __init__(self, server_url: str, debug: bool = False, timeout: int = 60):
        """
        Initialize an HTTP-Streaming MCP client.
        
        Args:
            server_url: The URL of the HTTP-Streaming MCP server
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
        logger.debug(f"Connecting to MCP server at {self.server_url} via HTTP-Streaming")
        
        # Create HTTP-Streaming transport
        self.transport = HTTPStreamingTransport(self.server_url)
        
        # Create a minimal session-like interface for HTTP-Streaming
        # This is a simplified implementation that works with the transport
        class HTTPStreamingSession:
            def __init__(self, transport):
                self.transport = transport
                
            async def initialize(self):
                """Initialize the session."""
                return await self.transport.send_and_receive({
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "0.1.0",
                        "clientInfo": {
                            "name": "praisonai-http-streaming",
                            "version": "1.0.0"
                        }
                    }
                })
                
            async def list_tools(self):
                """List available tools."""
                result = await self.transport.send_and_receive({
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {}
                })
                
                # Convert to expected format
                class ToolsResponse:
                    def __init__(self, tools):
                        self.tools = [type('Tool', (), tool)() for tool in tools]
                        
                return ToolsResponse(result.get('tools', []))
                
            async def call_tool(self, name: str, arguments: dict):
                """Call a tool."""
                result = await self.transport.send_and_receive({
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": name,
                        "arguments": arguments
                    }
                })
                
                # Convert to expected format
                class ToolResult:
                    def __init__(self, content):
                        self.content = content
                        
                content = result.get('content', [])
                if isinstance(content, str):
                    content = [type('TextContent', (), {'text': content})()]
                elif isinstance(content, list) and content and isinstance(content[0], str):
                    content = [type('TextContent', (), {'text': c})() for c in content]
                    
                return ToolResult(content)
        
        self.session = HTTPStreamingSession(self.transport)
        
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
            wrapper = HTTPStreamingMCPTool(
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