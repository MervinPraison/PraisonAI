import os
import logging
import asyncio
import time
import sys
import inspect
import json
from typing import List, Dict, Any, Optional, Callable
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.sse import sse_client

from praisonaiagents import Agent

# Set up logging based on environment variable
log_level = os.environ.get("LOGLEVEL", "info").upper()
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger("mcp-client")

# Create a custom prompt that explicitly mentions the tools
system_prompt = """You are a helpful assistant that can provide greetings and check weather information.

You have access to the following tools:
1. get_greeting(name: str) - Get a personalized greeting for a given name
2. get_weather(city: str) - Get weather information for a city (Paris, London, New York, Tokyo, Sydney)

When asked about weather, always use the get_weather tool with the appropriate city.
When asked for a greeting, always use the get_greeting tool with the appropriate name.
"""

# Global event loop for async operations
event_loop = None

def get_event_loop():
    """Get or create a global event loop."""
    global event_loop
    if event_loop is None or event_loop.is_closed():
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
    return event_loop

class SSEMCPTool:
    """A wrapper for an MCP tool that can be used with praisonaiagents."""
    
    def __init__(self, name: str, description: str, session: ClientSession, input_schema: Optional[Dict[str, Any]] = None):
        self.name = name
        self.__name__ = name  # Required for Agent to recognize it as a tool
        self.__qualname__ = name  # Required for Agent to recognize it as a tool
        self.__doc__ = description  # Required for Agent to recognize it as a tool
        self.description = description
        self.session = session
        self.input_schema = input_schema or {}
        
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
            return future.result(timeout=30)
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
    
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.session = None
        self.tools = []
        self._initialize()
        
    def _initialize(self):
        """Initialize the connection and tools."""
        # Use the global event loop
        loop = get_event_loop()
        
        # Start a background thread to run the event loop
        def run_event_loop():
            asyncio.set_event_loop(loop)
            loop.run_forever()
        
        import threading
        self.loop_thread = threading.Thread(target=run_event_loop, daemon=True)
        self.loop_thread.start()
        
        # Run the initialization in the event loop
        future = asyncio.run_coroutine_threadsafe(self._async_initialize(), loop)
        self.tools = future.result(timeout=30)
    
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
                input_schema=input_schema
            )
            tools.append(wrapper)
            
        return tools
    
    def __iter__(self):
        """Return an iterator over the tools."""
        return iter(self.tools)


def main():
    # Server URL
    server_url = "http://0.0.0.0:8080/sse"
    
    try:
        # Connect to the MCP server
        client = SSEMCPClient(server_url)
        
        if not client.tools:
            logger.error("No tools found on the server")
            return
            
        logger.info(f"Connected to server with {len(client.tools)} tools: {[tool.name for tool in client.tools]}")
        
        # Create OpenAI-compatible tool definitions
        openai_tools = [tool.to_openai_tool() for tool in client.tools]
        logger.debug(f"OpenAI tools: {json.dumps(openai_tools, indent=2)}")
        
        # Create an agent with the tools
        assistant_agent = Agent(
            instructions=system_prompt,
            llm="openai/gpt-4o-mini",
            tools=client.tools,
            verbose=True
        )
        
        # Start the agent with a query
        logger.info("Starting agent with query about weather in Paris")
        result = assistant_agent.chat(
            "Hello! Can you tell me what the weather is like in Paris today?",
            tools=openai_tools
        )
        
        logger.info(f"Agent response: {result}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()