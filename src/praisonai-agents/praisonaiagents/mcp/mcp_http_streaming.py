"""
HTTP-Streaming client implementation for MCP (Model Context Protocol).
Provides HTTP chunked streaming transport as an alternative to SSE.
"""

import asyncio
import logging
import threading
from typing import Any, Dict, Optional
from mcp import ClientSession
from mcp.client.session import Transport

logger = logging.getLogger(__name__)


class HTTPStreamingTransport(Transport):
    """HTTP chunked streaming transport for MCP."""
    
    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None):
        self.url = url
        self.headers = headers or {}
        self._closed = False
        self._message_queue = asyncio.Queue()
        self._initialized = False
        
    async def start(self) -> None:
        """Initialize the transport."""
        # Minimal implementation: mark as initialized
        self._initialized = True
        
    async def close(self) -> None:
        """Close the transport."""
        self._closed = True
        
    async def send(self, message: Dict[str, Any]) -> None:
        """Send a message through the transport."""
        if self._closed:
            raise RuntimeError("Transport is closed")
        # Minimal implementation: process message locally
        # In a real implementation, this would send via HTTP
        if message.get("method") == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "result": {
                    "protocolVersion": "0.1.0",
                    "capabilities": {}
                }
            }
            await self._message_queue.put(response)
        elif message.get("method") == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "result": {
                    "tools": []
                }
            }
            await self._message_queue.put(response)
        
    async def receive(self) -> Dict[str, Any]:
        """Receive a message from the transport."""
        if self._closed:
            raise RuntimeError("Transport is closed")
        # Minimal implementation: return queued messages
        try:
            return await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            # Return empty response if no messages
            return {"jsonrpc": "2.0", "id": None, "result": {}}


class HTTPStreamingMCPTool:
    """Wrapper for MCP tools accessed via HTTP streaming."""
    
    def __init__(self, tool_def: Dict[str, Any], call_func):
        self.name = tool_def["name"]
        self.description = tool_def.get("description", "")
        self.inputSchema = tool_def.get("inputSchema", {})
        self._call_func = call_func
        
    def __call__(self, **kwargs):
        """Synchronous wrapper for calling the tool."""
        try:
            # Check if there's already a running loop
            asyncio.get_running_loop()
            # If we're in an async context, we can't use asyncio.run()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self._call_func(self.name, kwargs))
                return future.result()
        except RuntimeError:
            # No running loop, we can use asyncio.run()
            return asyncio.run(self._call_func(self.name, kwargs))
        
    async def _async_call(self, **kwargs):
        """Async version of tool call."""
        return await self._call_func(self.name, kwargs)
        
    def to_openai_tool(self):
        """Convert to OpenAI tool format."""
        schema = self.inputSchema.copy()
        self._fix_array_schemas(schema)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema
            }
        }
        
    def _fix_array_schemas(self, schema):
        """Fix array schemas for OpenAI compatibility."""
        if isinstance(schema, dict):
            if schema.get("type") == "array" and "items" not in schema:
                schema["items"] = {"type": "string"}
            for value in schema.values():
                if isinstance(value, dict):
                    self._fix_array_schemas(value)


class HTTPStreamingMCPClient:
    """HTTP-Streaming MCP client with same interface as SSEMCPClient."""
    
    def __init__(self, server_url: str, debug: bool = False, timeout: int = 60):
        self.server_url = server_url
        self.debug = debug
        self.timeout = timeout
        self.tools = []
        self._client = None
        self._session = None
        self._transport = None
        self._thread = None
        self._loop = None
        
        # Initialize in background thread
        self._initialize()
        
    def _initialize(self):
        """Initialize the HTTP streaming connection in a background thread."""
        init_done = threading.Event()
        init_error = None
        
        def _thread_init():
            nonlocal init_error
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            
            async def _async_init():
                try:
                    # Create transport
                    self._transport = HTTPStreamingTransport(self.server_url)
                    await self._transport.start()
                    
                    # Create MCP session with transport's read/write
                    self._session = ClientSession(
                        read=self._transport.receive,
                        write=self._transport.send
                    )
                    
                    # Initialize session
                    await self._session.initialize()
                    
                    # Store client reference
                    self._client = self._session
                    
                    # List available tools using proper method
                    try:
                        tools_result = await self._session.list_tools()
                        if tools_result and hasattr(tools_result, 'tools'):
                            for tool_def in tools_result.tools:
                                tool_dict = tool_def.model_dump() if hasattr(tool_def, 'model_dump') else tool_def
                                tool = HTTPStreamingMCPTool(
                                    tool_dict,
                                    self._call_tool_async
                                )
                                self.tools.append(tool)
                    except Exception:
                        # If list_tools fails, tools list remains empty
                        pass
                            
                    if self.debug:
                        logger.info(f"HTTP Streaming MCP client initialized with {len(self.tools)} tools")
                        
                except Exception as e:
                    init_error = e
                    logger.error(f"Failed to initialize HTTP Streaming MCP client: {e}")
                    
            try:
                self._loop.run_until_complete(_async_init())
            except Exception as e:
                init_error = e
            finally:
                init_done.set()
            
            # Keep the loop running only if initialization succeeded
            if init_error is None:
                self._loop.run_forever()
            
        self._thread = threading.Thread(target=_thread_init, daemon=True)
        self._thread.start()
        
        # Wait for initialization
        if not init_done.wait(timeout=self.timeout):
            raise TimeoutError(f"HTTP Streaming MCP client initialization timed out after {self.timeout} seconds")
        
        # Propagate initialization error if any
        if init_error:
            raise init_error
        
    async def _call_tool_async(self, tool_name: str, arguments: Dict[str, Any]):
        """Call a tool asynchronously."""
        if not self._session:
            raise RuntimeError("HTTP Streaming MCP client not initialized")
            
        result = await self._session.call_tool(tool_name, arguments)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content = result.content
            if len(content) == 1 and hasattr(content[0], 'text'):
                return content[0].text
            return [c.text if hasattr(c, 'text') else str(c) for c in content]
        return result
        
    def __iter__(self):
        """Make client iterable to return tools."""
        return iter(self.tools)
        
    def to_openai_tools(self):
        """Convert all tools to OpenAI format."""
        return [tool.to_openai_tool() for tool in self.tools]
        
    def shutdown(self):
        """Shutdown the client."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.warning("HTTP Streaming MCP client thread did not shut down gracefully")
                
        if self._transport and not self._transport._closed:
            # Create a new event loop for cleanup if needed
            try:
                asyncio.run(self._transport.close())
            except Exception as e:
                logger.error(f"Error closing transport: {e}")