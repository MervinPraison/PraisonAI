"""
HTTP Stream client implementation for MCP (Model Context Protocol).
This module provides the necessary classes and functions to connect to an MCP server
over HTTP Stream transport, implementing the Streamable HTTP transport protocol.
"""

import asyncio
import logging
import threading
import inspect
import json
import time
import uuid
from typing import List, Dict, Any, Optional, Callable, Iterable, Union
from urllib.parse import urlparse, urljoin

from mcp import ClientSession
try:
    import aiohttp
except ImportError:
    raise ImportError("aiohttp is required for HTTP Stream transport. Install with: pip install praisonaiagents[mcp]")

logger = logging.getLogger("mcp-http-stream")

# Global event loop for async operations
_event_loop = None

def get_event_loop():
    """Get or create a global event loop."""
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_event_loop)
    return _event_loop


class HTTPStreamMCPTool:
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
                    annotation = Any
                
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


class HTTPStreamTransport:
    """
    HTTP Stream Transport implementation for MCP.
    
    This transport provides a single endpoint for all MCP communication,
    supporting both batch (JSON) and streaming (SSE) response modes.
    """
    
    def __init__(self, base_url: str, session_id: Optional[str] = None, options: Optional[Dict[str, Any]] = None):
        self.base_url = base_url
        self.session_id = session_id
        self.options = options or {}
        self.response_mode = self.options.get('responseMode', 'batch')
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream'
        }
        if session_id:
            self.headers['Mcp-Session-Id'] = session_id
        
        # Add custom headers if provided
        if 'headers' in self.options:
            self.headers.update(self.options['headers'])
        
        self._session = None
        self._sse_task = None
        self._message_queue = asyncio.Queue()
        self._pending_requests = {}
        self._closing = False
        
    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Set closing flag to stop listener gracefully
        self._closing = True
        
        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()
    
    async def send_request(self, request: Dict[str, Any]) -> Union[Dict[str, Any], None]:
        """Send a request to the HTTP Stream endpoint."""
        if not self._session:
            raise RuntimeError("Transport not initialized. Use async context manager.")
        
        try:
            async with self._session.post(self.base_url, json=request, headers=self.headers) as response:
                # Update session ID if provided in response
                if 'Mcp-Session-Id' in response.headers:
                    self.session_id = response.headers['Mcp-Session-Id']
                    self.headers['Mcp-Session-Id'] = self.session_id
                
                # Handle different response types
                content_type = response.headers.get('Content-Type', '')
                
                if 'text/event-stream' in content_type:
                    # Stream mode - process SSE events
                    return await self._process_sse_response(response)
                else:
                    # Batch mode - return JSON response
                    return await response.json()
                    
        except Exception as e:
            logger.error(f"Error sending request: {e}")
            raise
    
    async def _process_sse_response(self, response):
        """Process SSE response stream."""
        buffer = ""
        async for chunk in response.content:
            buffer += chunk.decode('utf-8')
            
            # Process complete SSE events
            while "\n\n" in buffer:
                event, buffer = buffer.split("\n\n", 1)
                lines = event.strip().split("\n")
                
                # Parse SSE event
                data = None
                for line in lines:
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix
                
                if data:
                    try:
                        message = json.loads(data)
                        # Process the message
                        if 'id' in message and message['id'] in self._pending_requests:
                            # This is a response to a pending request
                            self._pending_requests[message['id']].set_result(message)
                        else:
                            # This is a server-initiated message
                            await self._message_queue.put(message)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse SSE event: {data}")
    
    async def start_sse_listener(self):
        """Start listening for SSE events from the server."""
        if self._sse_task is None or self._sse_task.done():
            self._sse_task = asyncio.create_task(self._sse_listener())
    
    async def _sse_listener(self):
        """Background task to listen for SSE events."""
        while True:
            try:
                # Check if we should stop
                if hasattr(self, '_closing') and self._closing:
                    break
                    
                url = self.base_url
                if self.session_id:
                    # Add session as query parameter for SSE connection
                    url = f"{url}?session={self.session_id}"
                
                headers = {
                    'Accept': 'text/event-stream',
                    'Cache-Control': 'no-cache'
                }
                if self.session_id:
                    headers['Mcp-Session-Id'] = self.session_id
                
                async with self._session.get(url, headers=headers) as response:
                    buffer = ""
                    async for chunk in response.content:
                        # Check if we should stop
                        if hasattr(self, '_closing') and self._closing:
                            break
                            
                        buffer += chunk.decode('utf-8')
                        
                        # Process complete SSE events
                        while "\n\n" in buffer:
                            event, buffer = buffer.split("\n\n", 1)
                            lines = event.strip().split("\n")
                            
                            # Parse SSE event
                            data = None
                            for line in lines:
                                if line.startswith("data: "):
                                    data = line[6:]  # Remove "data: " prefix
                            
                            if data:
                                try:
                                    message = json.loads(data)
                                    await self._message_queue.put(message)
                                except json.JSONDecodeError:
                                    logger.error(f"Failed to parse SSE event: {data}")
                                
            except asyncio.CancelledError:
                # Proper shutdown
                break
            except Exception as e:
                if not (hasattr(self, '_closing') and self._closing):
                    logger.error(f"SSE listener error: {e}")
                    await asyncio.sleep(1)  # Reconnect after 1 second
                else:
                    break
    
    def read_stream(self):
        """Create a read stream for the ClientSession."""
        async def _read():
            while True:
                message = await self._message_queue.get()
                yield message
        return _read()
    
    def write_stream(self):
        """Create a write stream for the ClientSession."""
        async def _write(message):
            if hasattr(message, 'to_dict'):
                message = message.to_dict()
            response = await self.send_request(message)
            return response
        return _write


class HTTPStreamMCPClient:
    """A client for connecting to an MCP server over HTTP Stream transport."""
    
    def __init__(self, server_url: str, debug: bool = False, timeout: int = 60, options: Optional[Dict[str, Any]] = None):
        """
        Initialize an HTTP Stream MCP client.
        
        Args:
            server_url: The URL of the HTTP Stream MCP server
            debug: Whether to enable debug logging
            timeout: Timeout in seconds for operations (default: 60)
            options: Additional configuration options for the transport
        """
        # Parse URL to extract base URL and endpoint
        parsed = urlparse(server_url)
        
        # If the URL already has a path, use it; otherwise use default /mcp endpoint
        if parsed.path and parsed.path != '/':
            self.base_url = server_url
        else:
            # Default endpoint is /mcp
            self.base_url = urljoin(server_url, '/mcp')
        
        self.debug = debug
        self.timeout = timeout
        self.options = options or {}
        self.session = None
        self.tools = []
        self.transport = None
        
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
        logger.debug(f"Connecting to MCP server at {self.base_url}")
        
        # Create HTTP Stream transport
        self.transport = HTTPStreamTransport(self.base_url, options=self.options)
        await self.transport.__aenter__()
        
        # Create read and write streams
        read_stream = self.transport.read_stream()
        write_stream = self.transport.write_stream()
        
        # Start SSE listener if in stream mode
        if self.options.get('responseMode', 'batch') == 'stream':
            await self.transport.start_sse_listener()
        
        # Create client session
        self._session_context = ClientSession(read_stream, write_stream)
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
            wrapper = HTTPStreamMCPTool(
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
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.transport:
            await self.transport.__aexit__(exc_type, exc_val, exc_tb)
        if hasattr(self, '_session_context') and self._session_context:
            await self._session_context.__aexit__(exc_type, exc_val, exc_tb)