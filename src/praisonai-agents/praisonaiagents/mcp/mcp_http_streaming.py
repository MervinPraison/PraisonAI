"""
HTTP-Streaming client implementation for MCP (Model Context Protocol).
Provides HTTP chunked streaming transport as an alternative to SSE.
"""

import asyncio
import logging
import threading
import queue
import json
from typing import Any, Dict, List, Optional
from mcp import ClientSession
from mcp.client.session import Transport
from mcp.shared.memory import get_session_from_context

logger = logging.getLogger(__name__)


class HTTPStreamingTransport(Transport):
    """HTTP chunked streaming transport for MCP."""
    
    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None):
        self.url = url
        self.headers = headers or {}
        self._closed = False
        
    async def start(self) -> None:
        """Initialize the transport."""
        # TODO: Implement actual HTTP streaming connection
        # For now, this is a placeholder that follows the Transport interface
        pass
        
    async def close(self) -> None:
        """Close the transport."""
        self._closed = True
        
    async def send(self, message: Dict[str, Any]) -> None:
        """Send a message through the transport."""
        if self._closed:
            raise RuntimeError("Transport is closed")
        # TODO: Implement actual HTTP streaming send
        # This would send the message as a chunked HTTP request
        
    async def receive(self) -> Dict[str, Any]:
        """Receive a message from the transport."""
        if self._closed:
            raise RuntimeError("Transport is closed")
        # TODO: Implement actual HTTP streaming receive
        # This would read from the chunked HTTP response stream
        raise NotImplementedError("HTTP streaming receive not yet implemented")


class HTTPStreamingMCPTool:
    """Wrapper for MCP tools accessed via HTTP streaming."""
    
    def __init__(self, tool_def: Dict[str, Any], call_func):
        self.name = tool_def["name"]
        self.description = tool_def.get("description", "")
        self.inputSchema = tool_def.get("inputSchema", {})
        self._call_func = call_func
        
    def __call__(self, **kwargs):
        """Synchronous wrapper for calling the tool."""
        result_queue = queue.Queue()
        
        async def _async_call():
            try:
                result = await self._call_func(self.name, kwargs)
                result_queue.put(("success", result))
            except Exception as e:
                result_queue.put(("error", e))
                
        # Run in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(_async_call())
        finally:
            loop.close()
            
        status, result = result_queue.get()
        if status == "error":
            raise result
        return result
        
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
        
        def _thread_init():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            
            async def _async_init():
                try:
                    # Create transport
                    self._transport = HTTPStreamingTransport(self.server_url)
                    
                    # Create MCP client
                    self._client = ClientSession()
                    
                    # Initialize session with transport
                    await self._client.initialize(self._transport)
                    
                    # Store session in context
                    self._session = self._client
                    
                    # List available tools
                    tools_result = await self._client.call_tool("list-tools", {})
                    if tools_result and hasattr(tools_result, 'tools'):
                        for tool_def in tools_result.tools:
                            tool = HTTPStreamingMCPTool(
                                tool_def.model_dump(),
                                self._call_tool_async
                            )
                            self.tools.append(tool)
                            
                    if self.debug:
                        logger.info(f"HTTP Streaming MCP client initialized with {len(self.tools)} tools")
                        
                except Exception as e:
                    logger.error(f"Failed to initialize HTTP Streaming MCP client: {e}")
                    raise
                    
            self._loop.run_until_complete(_async_init())
            init_done.set()
            
            # Keep the loop running
            self._loop.run_forever()
            
        self._thread = threading.Thread(target=_thread_init, daemon=True)
        self._thread.start()
        
        # Wait for initialization
        init_done.wait(timeout=self.timeout)
        
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
        if self._loop and self._thread:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
            
        if self._transport and not self._transport._closed:
            async def _close():
                await self._transport.close()
                
            if self._loop:
                asyncio.run_coroutine_threadsafe(_close(), self._loop)