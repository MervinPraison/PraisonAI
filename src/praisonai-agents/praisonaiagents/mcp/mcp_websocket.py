"""
WebSocket Transport for MCP (Model Context Protocol).

This module provides WebSocket-based transport for connecting to MCP servers.
WebSocket transport offers:
- Long-lived bidirectional communication
- Better cloud provider support (hibernatable connections)
- Lower protocol overhead compared to HTTP
- Session persistence across network interruptions

This is an optional transport - the 'websockets' package is only imported
when ws:// or wss:// URLs are used, ensuring no performance impact on
existing stdio/SSE/HTTP transports.

Based on SEP-1288: WebSocket Transport for MCP (in review).
Protocol Revision: 2025-11-25
"""

import asyncio
import json
import logging
import threading
import inspect
import re
from typing import Any, Dict, Optional, List

logger = logging.getLogger("mcp-websocket")

# Import shared utilities for thread-safe event loop and schema fixing
from .mcp_schema_utils import ThreadLocalEventLoop, fix_array_schemas


def is_websocket_url(url: str) -> bool:
    """
    Check if a URL is a WebSocket URL.
    
    Args:
        url: The URL string to check
        
    Returns:
        True if the URL starts with ws:// or wss://, False otherwise
    """
    if not isinstance(url, str):
        return False
    return bool(re.match(r'^wss?://', url, re.IGNORECASE))


def calculate_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """
    Calculate exponential backoff delay for reconnection.
    
    Args:
        attempt: The retry attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap in seconds
        
    Returns:
        Delay in seconds for this attempt
    """
    delay = base_delay * (2 ** attempt)
    return min(delay, max_delay)


# Thread-local event loop for WebSocket operations (thread-safe)
_event_loop_manager = ThreadLocalEventLoop()


def get_event_loop():
    """Get or create a thread-local event loop for WebSocket operations."""
    return _event_loop_manager.get_loop()


class WebSocketTransport:
    """
    Low-level WebSocket transport for MCP communication.
    
    This class handles the WebSocket connection and JSON-RPC message framing.
    It supports:
    - Secure (wss://) and insecure (ws://) connections
    - Session ID management
    - Authentication via subprotocol or headers
    - Automatic reconnection with exponential backoff
    """
    
    def __init__(
        self,
        url: str,
        session_id: Optional[str] = None,
        auth_token: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 30.0,
        ping_interval: float = 30.0,
        ping_timeout: float = 10.0
    ):
        """
        Initialize WebSocket transport.
        
        Args:
            url: WebSocket URL (ws:// or wss://)
            session_id: Optional MCP session ID
            auth_token: Optional authentication token
            max_retries: Maximum reconnection attempts
            retry_delay: Base delay between retries (exponential backoff)
            timeout: Connection timeout in seconds
            ping_interval: Interval between ping messages (keepalive)
            ping_timeout: Timeout for ping response
        """
        self.url = url
        self.session_id = session_id
        self.auth_token = auth_token
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        
        self._ws = None
        self._closed = False
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._receive_task = None
    
    async def __aenter__(self):
        """Async context manager entry - establish connection."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close connection."""
        await self.close()
    
    async def connect(self):
        """Establish WebSocket connection."""
        try:
            # Lazy import websockets
            import websockets
        except ImportError:
            raise ImportError(
                "websockets package is required for WebSocket transport. "
                "Install it with: pip install websockets"
            )
        
        # Build connection options
        extra_headers = {}
        subprotocols = []
        
        # Add session ID if present
        if self.session_id:
            extra_headers['Mcp-Session-Id'] = self.session_id
        
        # Add auth token via subprotocol (SEP-1288 recommendation)
        if self.auth_token:
            # Smuggle auth token in subprotocol list
            # Format: "mcp-auth-<base64-encoded-token>"
            import base64
            encoded_token = base64.b64encode(self.auth_token.encode()).decode()
            subprotocols.append(f"mcp-auth-{encoded_token}")
        
        # Always include MCP subprotocol
        subprotocols.append("mcp")
        
        # Connect with retry logic
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                self._ws = await asyncio.wait_for(
                    websockets.connect(
                        self.url,
                        extra_headers=extra_headers if extra_headers else None,
                        subprotocols=subprotocols if subprotocols else None,
                        ping_interval=self.ping_interval,
                        ping_timeout=self.ping_timeout,
                        close_timeout=10
                    ),
                    timeout=self.timeout
                )
                logger.debug(f"WebSocket connected to {self.url}")
                
                # Start background receive task
                self._receive_task = asyncio.create_task(self._receive_loop())
                return
                
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = calculate_backoff(attempt, self.retry_delay)
                    logger.warning(f"WebSocket connection failed, retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                else:
                    raise ConnectionError(f"Failed to connect after {self.max_retries + 1} attempts: {last_error}")
    
    async def _receive_loop(self):
        """Background task to receive messages and queue them."""
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    await self._message_queue.put(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse WebSocket message: {e}")
        except Exception as e:
            if not self._closed:
                logger.error(f"WebSocket receive error: {e}")
                await self._message_queue.put({"error": str(e)})
    
    async def send(self, message: Dict[str, Any]):
        """
        Send a JSON-RPC message over WebSocket.
        
        Args:
            message: JSON-RPC message dictionary
        """
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        
        data = json.dumps(message)
        await self._ws.send(data)
        logger.debug(f"Sent: {message.get('method', message.get('id', 'response'))}")
    
    async def receive(self) -> Dict[str, Any]:
        """
        Receive a JSON-RPC message from WebSocket.
        
        Returns:
            Parsed JSON-RPC message dictionary
        """
        message = await self._message_queue.get()
        if "error" in message and len(message) == 1:
            raise ConnectionError(message["error"])
        return message
    
    async def close(self):
        """Close WebSocket connection."""
        self._closed = True
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        logger.debug("WebSocket connection closed")


class WebSocketMCPTool:
    """
    A wrapper for an MCP tool that can be used with praisonaiagents.
    
    This class wraps a tool from a WebSocket MCP server and makes it
    compatible with the Agent class tool interface.
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        session: Any,  # ClientSession from mcp package
        input_schema: Optional[Dict[str, Any]] = None,
        timeout: int = 60
    ):
        """
        Initialize WebSocket MCP tool wrapper.
        
        Args:
            name: Tool name
            description: Tool description
            session: MCP ClientSession for making calls
            input_schema: JSON Schema for tool input
            timeout: Timeout for tool calls in seconds
        """
        self.name = name
        self.__name__ = name
        self.__qualname__ = name
        self.__doc__ = description
        self.description = description
        self.session = session
        self.input_schema = input_schema or {}
        self.timeout = timeout
        
        # Build function signature from input schema
        self.__signature__ = self._build_signature()
    
    def _build_signature(self) -> inspect.Signature:
        """Build function signature from input schema."""
        params = []
        
        if self.input_schema and 'properties' in self.input_schema:
            required = self.input_schema.get('required', [])
            
            for param_name, prop_schema in self.input_schema['properties'].items():
                # Determine type annotation
                prop_type = prop_schema.get('type', 'string') if isinstance(prop_schema, dict) else 'string'
                annotation = self._json_type_to_python(prop_type)
                
                # Determine default value
                default = inspect.Parameter.empty if param_name in required else None
                
                params.append(
                    inspect.Parameter(
                        name=param_name,
                        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        default=default,
                        annotation=annotation
                    )
                )
        
        return inspect.Signature(params)
    
    def _json_type_to_python(self, json_type: str) -> type:
        """Convert JSON Schema type to Python type."""
        type_map = {
            'string': str,
            'integer': int,
            'number': float,
            'boolean': bool,
            'array': list,
            'object': dict
        }
        return type_map.get(json_type, Any)
    
    def __call__(self, **kwargs):
        """
        Call the tool synchronously.
        
        This wraps the async call for synchronous usage.
        """
        logger.debug(f"Tool {self.name} called with args: {kwargs}")
        
        loop = get_event_loop()
        future = asyncio.run_coroutine_threadsafe(self._async_call(**kwargs), loop)
        
        try:
            return future.result(timeout=self.timeout)
        except Exception as e:
            logger.error(f"Error calling tool {self.name}: {e}")
            return f"Error: {str(e)}"
    
    async def _async_call(self, **kwargs):
        """Call the tool asynchronously."""
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
    
    def to_openai_tool(self) -> Dict[str, Any]:
        """Convert the tool to OpenAI function calling format."""
        # Fix array schemas to include 'items' attribute (using shared utility)
        fixed_schema = fix_array_schemas(self.input_schema)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": fixed_schema
            }
        }


class WebSocketMCPClient:
    """
    High-level client for connecting to MCP servers over WebSocket.
    
    This client handles:
    - Connection establishment and lifecycle
    - Tool discovery and wrapping
    - Session management
    - Automatic reconnection
    
    Example:
        ```python
        from praisonaiagents.mcp.mcp_websocket import WebSocketMCPClient
        
        client = WebSocketMCPClient("ws://localhost:8080/mcp")
        for tool in client.tools:
            print(tool.name)
        ```
    """
    
    def __init__(
        self,
        server_url: str,
        debug: bool = False,
        timeout: int = 60,
        auth_token: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize WebSocket MCP client.
        
        Args:
            server_url: WebSocket URL (ws:// or wss://)
            debug: Enable debug logging
            timeout: Timeout for operations in seconds
            auth_token: Optional authentication token
            options: Additional configuration options
        """
        self.server_url = server_url
        self.debug = debug
        self.timeout = timeout
        self.auth_token = auth_token
        self.options = options or {}
        
        self.session = None
        self.transport = None
        self.tools: List[WebSocketMCPTool] = []
        self._closed = False
        
        # Configure logging
        if debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.WARNING)
        
        # Initialize connection
        self._initialize()
    
    def _initialize(self):
        """Initialize the connection and discover tools."""
        loop = get_event_loop()
        
        # Start event loop in background thread if not running
        def run_event_loop():
            asyncio.set_event_loop(loop)
            loop.run_forever()
        
        self.loop_thread = threading.Thread(target=run_event_loop, daemon=True)
        self.loop_thread.start()
        
        # Run initialization
        future = asyncio.run_coroutine_threadsafe(self._async_initialize(), loop)
        self.tools = future.result(timeout=self.timeout)
    
    async def _async_initialize(self):
        """Asynchronously initialize connection and discover tools."""
        logger.debug(f"Connecting to MCP server at {self.server_url}")
        
        # Lazy import mcp package
        try:
            from mcp import ClientSession
        except ImportError:
            raise ImportError(
                "mcp package is required. Install it with: pip install mcp"
            )
        
        # Create transport
        self.transport = WebSocketTransport(
            self.server_url,
            auth_token=self.auth_token,
            timeout=self.timeout
        )
        await self.transport.connect()
        
        # Create read/write streams for ClientSession
        # The ClientSession expects async iterators for read/write
        read_stream = self._create_read_stream()
        write_stream = self._create_write_stream()
        
        # Create and initialize session
        self._session_context = ClientSession(read_stream, write_stream)
        self.session = await self._session_context.__aenter__()
        
        await self.session.initialize()
        
        # Discover tools
        logger.debug("Listing tools...")
        response = await self.session.list_tools()
        tools_data = response.tools
        logger.debug(f"Found {len(tools_data)} tools: {[t.name for t in tools_data]}")
        
        # Create tool wrappers
        tools = []
        for tool in tools_data:
            input_schema = tool.inputSchema if hasattr(tool, 'inputSchema') else None
            wrapper = WebSocketMCPTool(
                name=tool.name,
                description=tool.description if hasattr(tool, 'description') else f"Call the {tool.name} tool",
                session=self.session,
                input_schema=input_schema,
                timeout=self.timeout
            )
            tools.append(wrapper)
        
        return tools
    
    def _create_read_stream(self):
        """Create async iterator for reading from transport."""
        async def read():
            while not self._closed:
                try:
                    message = await self.transport.receive()
                    yield message
                except Exception as e:
                    if not self._closed:
                        logger.error(f"Read error: {e}")
                    break
        return read()
    
    def _create_write_stream(self):
        """Create write function for transport."""
        async def write(message):
            if hasattr(message, 'to_dict'):
                message = message.to_dict()
            await self.transport.send(message)
        return write
    
    def __iter__(self):
        """Return iterator over tools."""
        return iter(self.tools)
    
    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """Convert all tools to OpenAI format."""
        return [tool.to_openai_tool() for tool in self.tools]
    
    async def aclose(self):
        """Async cleanup."""
        if self._closed:
            return
        
        self._closed = True
        
        try:
            if hasattr(self, '_session_context') and self._session_context:
                await self._session_context.__aexit__(None, None, None)
        except Exception:
            pass
        
        try:
            if self.transport:
                await self.transport.close()
        except Exception:
            pass
    
    def close(self):
        """Synchronous cleanup."""
        if self._closed:
            return
        
        try:
            loop = get_event_loop()
            if not loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(self.aclose(), loop)
                future.result(timeout=5)
        except Exception:
            self._closed = True
    
    def __del__(self):
        """Cleanup on garbage collection."""
        try:
            if not self._closed:
                self.close()
        except Exception:
            pass
