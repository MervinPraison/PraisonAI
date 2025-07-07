"""
HTTP-Streaming client implementation for MCP (Model Context Protocol).
This module provides the necessary classes and functions to connect to an MCP server
over HTTP using chunked transfer encoding for bidirectional streaming.
"""

import asyncio
import json
import logging
import threading
import inspect
from typing import List, Dict, Any, Optional, Iterable, AsyncIterator
import httpx
from mcp import ClientSession

logger = logging.getLogger("mcp-http-streaming")

# Global event loop and lock for ensuring singleton pattern
_loop = None
_loop_lock = threading.Lock()


def get_or_create_event_loop():
    """Get the existing event loop or create a new one if it doesn't exist."""
    global _loop
    with _loop_lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, daemon=True).start()
    return _loop


class HTTPStreamingTransport:
    """HTTP chunked streaming transport for MCP."""
    
    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None):
        self.url = url
        self.headers = headers or {}
        self.client = httpx.AsyncClient(timeout=60.0)
        self.read_stream = None
        self.write_stream = None
        self._closed = False
        
    async def connect(self) -> tuple:
        """Establish bidirectional streaming connection."""
        # Create read and write stream adapters
        self.read_stream = HTTPReadStream(self)
        self.write_stream = HTTPWriteStream(self)
        
        # Initialize the streaming connection
        await self._initialize_connection()
        
        return (self.read_stream, self.write_stream)
    
    async def _initialize_connection(self):
        """Initialize the HTTP streaming connection."""
        # Send initial connection request
        headers = {
            **self.headers,
            "Content-Type": "application/json",
            "Transfer-Encoding": "chunked",
            "Accept": "application/x-ndjson"
        }
        
        # Start the bidirectional stream
        self._request_queue = asyncio.Queue()
        self._response_queue = asyncio.Queue()
        
        # Start background task for handling the stream
        asyncio.create_task(self._handle_stream(headers))
    
    async def _handle_stream(self, headers: Dict[str, str]):
        """Handle the bidirectional HTTP stream."""
        try:
            async with self.client.stream(
                "POST",
                f"{self.url}/mcp/v1/stream",
                headers=headers,
                content=self._request_iterator()
            ) as response:
                # Process response stream
                buffer = b""
                async for chunk in response.aiter_bytes():
                    buffer += chunk
                    # Process complete lines
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        if line.strip():
                            try:
                                message = json.loads(line.decode('utf-8'))
                                await self._response_queue.put(message)
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Stream error: {e}")
            self._closed = True
    
    async def _request_iterator(self) -> AsyncIterator[bytes]:
        """Generate request chunks from the queue."""
        while not self._closed:
            try:
                message = await asyncio.wait_for(
                    self._request_queue.get(), 
                    timeout=0.1
                )
                if message is None:
                    break
                chunk = json.dumps(message).encode('utf-8') + b'\n'
                yield chunk
            except asyncio.TimeoutError:
                continue
    
    async def send_message(self, message: Dict[str, Any]):
        """Send a message through the stream."""
        if not self._closed:
            await self._request_queue.put(message)
    
    async def receive_message(self) -> Optional[Dict[str, Any]]:
        """Receive a message from the stream."""
        if self._closed:
            return None
        try:
            return await self._response_queue.get()
        except Exception:
            return None
    
    async def close(self):
        """Close the transport."""
        self._closed = True
        if self._request_queue:
            await self._request_queue.put(None)
        await self.client.aclose()


class HTTPReadStream:
    """Read stream adapter for MCP."""
    
    def __init__(self, transport: HTTPStreamingTransport):
        self.transport = transport
    
    async def read(self) -> Optional[bytes]:
        """Read a message from the stream."""
        message = await self.transport.receive_message()
        if message:
            return json.dumps(message).encode('utf-8')
        return None


class HTTPWriteStream:
    """Write stream adapter for MCP."""
    
    def __init__(self, transport: HTTPStreamingTransport):
        self.transport = transport
    
    async def write(self, data: bytes):
        """Write a message to the stream."""
        try:
            message = json.loads(data.decode('utf-8'))
            await self.transport.send_message(message)
        except json.JSONDecodeError:
            logger.error("Failed to decode message for sending")


class HTTPStreamingMCPTool:
    """A wrapper for an MCP tool that can be used with praisonaiagents."""
    
    def __init__(
        self, 
        name: str, 
        description: str, 
        session: ClientSession, 
        input_schema: Optional[Dict[str, Any]] = None,
        timeout: int = 60
    ):
        """
        Initialize an MCP tool wrapper.
        
        Args:
            name: The name of the tool
            description: A description of what the tool does
            session: The MCP client session
            input_schema: The JSON schema for the tool's input parameters
            timeout: Timeout in seconds for tool calls (default: 60)
        """
        self.name = name
        self.description = description
        self.session = session
        self.input_schema = input_schema or {}
        self.timeout = timeout
        
        # Create the function signature dynamically
        self._create_signature()
    
    def _create_signature(self):
        """Create a function signature based on the input schema."""
        properties = self.input_schema.get("properties", {})
        required = self.input_schema.get("required", [])
        
        # Build parameter list
        params = []
        for prop_name, prop_schema in properties.items():
            param_type = prop_schema.get("type", "str")
            # Convert JSON schema types to Python types
            type_mapping = {
                "string": str,
                "number": float,
                "integer": int,
                "boolean": bool,
                "array": list,
                "object": dict,
            }
            param_type = type_mapping.get(param_type, Any)
            
            if prop_name in required:
                params.append(inspect.Parameter(
                    prop_name, 
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=param_type
                ))
            else:
                default_value = prop_schema.get("default", None)
                params.append(inspect.Parameter(
                    prop_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=default_value,
                    annotation=param_type
                ))
        
        # Create signature
        self.__signature__ = inspect.Signature(params)
    
    def __call__(self, **kwargs) -> Any:
        """Execute the tool with the given arguments."""
        # Run the async function in the event loop
        loop = get_or_create_event_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._async_call(**kwargs), 
            loop
        )
        return future.result(timeout=self.timeout)
    
    async def _async_call(self, **kwargs) -> Any:
        """Async implementation of the tool call."""
        try:
            result = await self.session.call_tool(self.name, kwargs)
            # Extract content from result
            if hasattr(result, 'content') and result.content:
                # Handle different content types
                for content_item in result.content:
                    if hasattr(content_item, 'text'):
                        return content_item.text
                    elif hasattr(content_item, 'data'):
                        return content_item.data
            return result
        except Exception as e:
            logger.error(f"Error calling tool {self.name}: {e}")
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
    
    def to_openai_tool(self) -> Dict[str, Any]:
        """Convert this tool to OpenAI function calling format."""
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
    """HTTP-Streaming MCP client with same interface as SSEMCPClient."""
    
    def __init__(self, server_url: str, debug: bool = False, timeout: int = 60, headers: Optional[Dict[str, str]] = None):
        """
        Initialize an HTTP-Streaming MCP client.
        
        Args:
            server_url: The URL of the HTTP MCP server
            debug: Whether to enable debug logging
            timeout: Timeout in seconds for operations (default: 60)
            headers: Optional headers to include in requests
        """
        self.server_url = server_url.rstrip('/')
        self.debug = debug
        self.timeout = timeout
        self.headers = headers or {}
        self.tools: List[HTTPStreamingMCPTool] = []
        self.session: Optional[ClientSession] = None
        
        # Set up logging
        if debug:
            logger.setLevel(logging.DEBUG)
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('[%(name)s] %(message)s'))
            logger.addHandler(handler)
        
        # Initialize in event loop
        loop = get_or_create_event_loop()
        future = asyncio.run_coroutine_threadsafe(self._initialize(), loop)
        future.result(timeout=timeout)
    
    async def _initialize(self):
        """Initialize the MCP session and discover tools."""
        try:
            # Create transport
            transport = HTTPStreamingTransport(self.server_url, self.headers)
            
            # Create session
            self.session = ClientSession()
            
            # Connect transport
            read_stream, write_stream = await transport.connect()
            
            # Initialize session with transport
            await self.session.initialize(read_stream, write_stream)
            
            # Get available tools
            tools_list = await self.session.list_tools()
            
            # Create tool wrappers
            for tool_info in tools_list.tools:
                tool = HTTPStreamingMCPTool(
                    name=tool_info.name,
                    description=tool_info.description or "",
                    session=self.session,
                    input_schema=tool_info.inputSchema if hasattr(tool_info, 'inputSchema') else {},
                    timeout=self.timeout
                )
                self.tools.append(tool)
            
            if self.debug:
                logger.debug(f"Initialized with {len(self.tools)} tools: {[t.name for t in self.tools]}")
                
        except Exception as e:
            logger.error(f"Failed to initialize HTTP-Streaming MCP client: {e}")
            raise
    
    def __iter__(self) -> Iterable[HTTPStreamingMCPTool]:
        """Iterate over available tools."""
        return iter(self.tools)
    
    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """Convert all tools to OpenAI function calling format."""
        return [tool.to_openai_tool() for tool in self.tools]
    
    async def close(self):
        """Close the MCP session."""
        if self.session:
            await self.session.close()