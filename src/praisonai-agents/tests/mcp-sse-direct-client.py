# python mcp-sse-direct-client.py http://0.0.0.0:8080/sse
import asyncio
import json
import os
import sys
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.sse import sse_client

from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env

class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()

    async def connect_to_sse_server(self, server_url: str):
        """Connect to an MCP server running with SSE transport"""
        # Store the context managers so they stay alive
        self._streams_context = sse_client(url=server_url)
        streams = await self._streams_context.__aenter__()

        self._session_context = ClientSession(*streams)
        self.session: ClientSession = await self._session_context.__aenter__()

        # Initialize
        await self.session.initialize()

        # List available tools to verify connection
        print("Initialized SSE client...")
        print("Listing tools...")
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])
        
        # Print tool descriptions
        for tool in tools:
            print(f"\n{tool.name}: {tool.description}")
            if hasattr(tool, 'inputSchema') and tool.inputSchema:
                print(f"  Parameters: {json.dumps(tool.inputSchema, indent=2)}")

    async def cleanup(self):
        """Properly clean up the session and streams"""
        if hasattr(self, '_session_context'):
            await self._session_context.__aexit__(None, None, None)
        if hasattr(self, '_streams_context'):
            await self._streams_context.__aexit__(None, None, None)

    async def process_query(self, query: str) -> str:
        """Process a query by directly calling the appropriate tool"""
        query = query.strip().lower()
        
        if query.startswith("hello") or query.startswith("hi"):
            # Extract name or use a default
            parts = query.split()
            name = parts[1] if len(parts) > 1 else "there"
            
            # Call the greeting tool
            print(f"\nCalling get_greeting with name: {name}")
            result = await self.session.call_tool("get_greeting", {"name": name})
            return result.content[0].text if hasattr(result, 'content') and result.content else str(result)
        
        elif "weather" in query:
            # Try to extract city name
            city = None
            for known_city in ["Paris", "London", "New York", "Tokyo", "Sydney"]:
                if known_city.lower() in query.lower():
                    city = known_city
                    break
            
            if not city:
                return "I couldn't identify a city in your query. Please mention a city like Paris, London, New York, Tokyo, or Sydney."
            
            # Call the weather tool
            print(f"\nCalling get_weather with city: {city}")
            result = await self.session.call_tool("get_weather", {"city": city})
            return result.content[0].text if hasattr(result, 'content') and result.content else str(result)
        
        else:
            return "I can help with greetings or weather information. Try asking something like 'Hello John' or 'What's the weather in Paris?'"

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                    
                response = await self.process_query(query)
                print("\n" + response)
                    
            except Exception as e:
                print(f"\nError: {str(e)}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <URL of SSE MCP server (i.e. http://localhost:8081/sse)>")
        sys.exit(1)

    client = MCPClient()
    try:
        await client.connect_to_sse_server(server_url=sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main()) 