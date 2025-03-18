import asyncio
import json
from typing import Dict, Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Define server configuration
server_params = StdioServerParameters(
      command="/Users/praison/miniconda3/envs/mcp/bin/python",
      args=[
          "/Users/praison/stockprice/app.py",
      ],
  )

async def execute_tool(session: ClientSession, tool_name: str, params: Dict[str, Any]) -> Any:
    """
    Execute a tool with proper error handling and return the result.
    
    This follows the pattern shown in the article for reliable tool execution.
    """
    try:
        result = await session.call_tool(tool_name, arguments=params)
        return result
    except Exception as e:
        print(f"Error executing tool {tool_name}: {str(e)}")
        return {"error": str(e)}

async def main():
    # Start server and connect client
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()
            
            # Get details of available tools
            tools_result = await session.list_tools()
            tools = tools_result.tools
            
            # Print available tools for debugging
            print(f"Available tools: {[tool.name for tool in tools]}")
            
            # Example: Call a tool if it exists
            if tools and len(tools) > 0:
                # Assuming first tool as an example
                tool = tools[0]
                print(f"Calling tool: {tool.name}")
                print(f"Tool schema: {json.dumps(tool.inputSchema, indent=2)}")
                
                # Create parameters based on the tool's input schema
                # This is a simplification - in a real application, you would parse
                # the schema and provide appropriate values
                params = {}
                
                # For demonstration, we'll check if the tool needs any parameters
                if tool.inputSchema and "properties" in tool.inputSchema:
                    # Just populate with empty values for demonstration
                    params = {
                        key: "" for key in tool.inputSchema["properties"].keys()
                    }
                
                # Call the tool with appropriate parameters
                response = await execute_tool(session, tool.name, params)
                
                # Process the response
                print(f"Tool response: {response}")

# Run the async function
if __name__ == "__main__":
    asyncio.run(main())