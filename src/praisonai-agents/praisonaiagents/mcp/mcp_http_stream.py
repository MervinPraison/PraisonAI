"""
HTTP Stream client implementation for MCP (Model Context Protocol).
This module provides the necessary classes and functions to connect to an MCP server
over HTTP Stream transport, implementing the Streamable HTTP transport protocol.
"""

import asyncio
import atexit
import logging
import threading
import inspect
import json
import time
import uuid
import weakref
from typing import List, Dict, Any, Optional, Callable, Iterable, Union
from urllib.parse import urlparse, urljoin

try:
    from mcp import ClientSession
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    ClientSession = None

try:
    import aiohttp
except ImportError:
    aiohttp = None

logger = logging.getLogger("mcp-http-stream")

# Import shared utilities for thread-safe event loop and schema fixing
from .mcp_schema_utils import ThreadLocalEventLoop, fix_array_schemas

# Thread-local event loop for async operations (thread-safe)
_event_loop_manager = ThreadLocalEventLoop()

# Global registry of active clients for cleanup
_active_clients = weakref.WeakSet()
_cleanup_registered = False

def get_event_loop():
    """Get or create a thread-local event loop."""
    return _event_loop_manager.get_loop()


def _cleanup_all_clients():
    """Clean up all active clients at program exit."""
    if not _active_clients:
        return
    
    # Create a copy to avoid modification during iteration
    clients_to_cleanup = list(_active_clients)
    
    for client in clients_to_cleanup:
        try:
            if hasattr(client, '_force_cleanup'):
                client._force_cleanup()
        except Exception:
            # Ignore exceptions during cleanup
            pass


def _register_cleanup():
    """Register the cleanup function to run at program exit."""
    global _cleanup_registered
    if not _cleanup_registered:
        atexit.register(_cleanup_all_clients)
        _cleanup_registered = True


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
    
    def to_openai_tool(self):
        """Convert the tool to OpenAI format."""
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


class HTTPStreamTransport:
    """
    HTTP Stream Transport implementation for MCP.
    
    This transport provides a single endpoint for all MCP communication,
    supporting both batch (JSON) and streaming (SSE) response modes.
    
    Per MCP Protocol Revision 2025-11-25:
    - Includes MCP-Protocol-Version header on all requests
    - Handles session management via Mcp-Session-Id header
    - Supports SSE resumability via Last-Event-ID
    """
    
    # Default protocol version for backward compatibility
    DEFAULT_PROTOCOL_VERSION = '2025-03-26'
    
    def __init__(self, base_url: str, session_id: Optional[str] = None, options: Optional[Dict[str, Any]] = None):
        self.base_url = base_url
        self.session_id = session_id
        self.options = options or {}
        self.response_mode = self.options.get('responseMode', 'batch')
        self.protocol_version = self.options.get('protocol_version', self.DEFAULT_PROTOCOL_VERSION)
        
        # Track last event ID for resumability
        self.last_event_id: Optional[str] = None
        self._retry_delay_ms: int = 3000  # Default retry delay
        
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
            'Mcp-Protocol-Version': self.protocol_version  # Required per spec
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
        self._closed = False
        
    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Prevent double closing
        if self._closed:
            return
        
        # Set closing flag to stop listener gracefully
        self._closing = True
        self._closed = True
        
        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()
    
    def __del__(self):
        """Lightweight cleanup during garbage collection."""
        # Note: We cannot safely run async cleanup in __del__
        # The best practice is to use async context managers or explicit close() calls
        pass
    
    
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
        """Process SSE response stream with resumability support."""
        buffer = ""
        async for chunk in response.content:
            buffer += chunk.decode('utf-8')
            
            # Process complete SSE events
            while "\n\n" in buffer:
                event, buffer = buffer.split("\n\n", 1)
                lines = event.strip().split("\n")
                
                # Parse SSE event fields per spec
                event_id = None
                data_lines = []
                retry_value = None
                
                for line in lines:
                    if line.startswith("id:"):
                        # Track event ID for resumability
                        event_id = line[3:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                    elif line.startswith("retry:"):
                        # Handle retry field per SSE spec
                        try:
                            retry_value = int(line[6:].strip())
                        except ValueError:
                            pass
                
                # Update last event ID for resumability
                if event_id:
                    self.last_event_id = event_id
                
                # Update retry delay if provided
                if retry_value is not None:
                    self._retry_delay_ms = retry_value
                
                # Process data if present
                data = '\n'.join(data_lines) if data_lines else None
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
    
    async def terminate_session(self) -> bool:
        """
        Terminate the session via HTTP DELETE.
        
        Per MCP spec: Clients that no longer need a particular session
        SHOULD send an HTTP DELETE to the MCP endpoint with the
        Mcp-Session-Id header to explicitly terminate the session.
        
        Returns:
            True if session was terminated, False if server doesn't support it
        """
        if not self._session or not self.session_id:
            return False
        
        try:
            headers = {
                'Mcp-Session-Id': self.session_id,
                'Mcp-Protocol-Version': self.protocol_version
            }
            async with self._session.delete(self.base_url, headers=headers) as response:
                if response.status == 405:
                    # Server doesn't allow client-initiated session termination
                    logger.debug("Server does not allow session termination via DELETE")
                    return False
                elif response.status in (200, 202, 204):
                    # Session terminated successfully
                    self.session_id = None
                    self.headers.pop('Mcp-Session-Id', None)
                    return True
                else:
                    logger.warning(f"Unexpected response to DELETE: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Error terminating session: {e}")
            return False
    
    async def start_sse_listener(self):
        """Start listening for SSE events from the server."""
        if self._sse_task is None or self._sse_task.done():
            self._sse_task = asyncio.create_task(self._sse_listener())
    
    async def _sse_listener(self):
        """Background task to listen for SSE events with resumability support."""
        while True:
            try:
                # Check if we should stop
                if hasattr(self, '_closing') and self._closing:
                    break
                    
                url = self.base_url
                
                # Build headers per MCP spec
                headers = {
                    'Accept': 'text/event-stream',
                    'Cache-Control': 'no-cache',
                    'Mcp-Protocol-Version': self.protocol_version  # Required per spec
                }
                if self.session_id:
                    headers['Mcp-Session-Id'] = self.session_id
                
                # Include Last-Event-ID for resumability per spec
                if self.last_event_id:
                    headers['Last-Event-ID'] = self.last_event_id
                
                async with self._session.get(url, headers=headers) as response:
                    # Handle session expiration (HTTP 404)
                    if response.status == 404:
                        logger.warning("Session expired (HTTP 404), need to reinitialize")
                        self.session_id = None
                        self.headers.pop('Mcp-Session-Id', None)
                        break
                    
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
                            
                            # Parse SSE event fields
                            event_id = None
                            data_lines = []
                            retry_value = None
                            
                            for line in lines:
                                if line.startswith("id:"):
                                    event_id = line[3:].strip()
                                elif line.startswith("data:"):
                                    data_lines.append(line[5:].strip())
                                elif line.startswith("retry:"):
                                    try:
                                        retry_value = int(line[6:].strip())
                                    except ValueError:
                                        pass
                            
                            # Update last event ID for resumability
                            if event_id:
                                self.last_event_id = event_id
                            
                            # Update retry delay if provided
                            if retry_value is not None:
                                self._retry_delay_ms = retry_value
                            
                            # Process data
                            data = '\n'.join(data_lines) if data_lines else None
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
                    # Use retry delay from server or default
                    await asyncio.sleep(self._retry_delay_ms / 1000.0)
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
        # Check if MCP is available
        if not MCP_AVAILABLE:
            raise ImportError(
                "MCP (Model Context Protocol) package is not installed. "
                "Install it with: pip install praisonaiagents[mcp]"
            )

        # Check if aiohttp is available
        if aiohttp is None:
            raise ImportError(
                "aiohttp is required for HTTP Stream transport. "
                "Install it with: pip install praisonaiagents[mcp]"
            )

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
        self._closed = False
        
        # Set up logging
        if debug:
            logger.setLevel(logging.DEBUG)
        else:
            # Set to WARNING by default to hide INFO messages
            logger.setLevel(logging.WARNING)
        
        # Register this client for cleanup and setup exit handler
        _active_clients.add(self)
        _register_cleanup()
        
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
        
        # Set up cleanup finalizer now that transport and session are created
        self._finalizer = weakref.finalize(self, self._static_cleanup, 
                                         self.transport, self._session_context)
            
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
        await self.aclose()
    
    async def aclose(self):
        """Async cleanup method to close all resources."""
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
                await self.transport.__aexit__(None, None, None)
        except Exception:
            pass
    
    def close(self):
        """Synchronous cleanup method to close all resources."""
        if self._closed:
            return
            
        try:
            # Use the global event loop for non-blocking cleanup
            loop = get_event_loop()
            if not loop.is_closed():
                # Schedule cleanup without blocking - add callback for fallback
                future = asyncio.run_coroutine_threadsafe(self.aclose(), loop)
                
                # Add a completion callback for fallback cleanup if async fails
                def _cleanup_callback(fut):
                    try:
                        fut.result()  # This will raise if aclose() failed
                    except Exception:
                        # If async cleanup failed, try force cleanup
                        try:
                            self._force_cleanup()
                        except Exception:
                            pass
                
                future.add_done_callback(_cleanup_callback)
            else:
                # Event loop is closed, use force cleanup immediately
                self._force_cleanup()
        except Exception:
            # If async scheduling fails, try force cleanup
            self._force_cleanup()
    
    def _force_cleanup(self):
        """Force cleanup of resources synchronously (for emergencies)."""
        if self._closed:
            return
            
        self._closed = True
        
        # Force close transport session if it exists
        try:
            if self.transport and hasattr(self.transport, '_session') and self.transport._session:
                session = self.transport._session
                if not session.closed:
                    # Force close the aiohttp session
                    if hasattr(session, '_connector') and session._connector:
                        try:
                            # Close connector directly
                            session._connector.close()
                        except Exception:
                            pass
        except Exception:
            pass
    
    @staticmethod
    def _static_cleanup(transport, session_context):
        """Static cleanup method for weakref finalizer."""
        try:
            # This is called by weakref finalizer, so we can't do async operations
            # Just ensure any session is closed if possible
            if transport and hasattr(transport, '_session') and transport._session:
                session = transport._session
                if not session.closed and hasattr(session, '_connector'):
                    try:
                        session._connector.close()
                    except Exception:
                        pass
        except Exception:
            pass
    
    def __del__(self):
        """Cleanup when object is garbage collected."""
        try:
            if not self._closed:
                self._force_cleanup()
        except Exception:
            # Never raise exceptions in __del__
            pass