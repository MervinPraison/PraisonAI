from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)  # Replace with your actual API key setup


# Create server parameters for stdio connection
server_params = StdioServerParameters(
    command="npx",  # Executable
    args=[
        "-y",
        "@openbnb/mcp-server-airbnb",
        "--ignore-robots-txt",
    ],  # Optional command line arguments
    env=None,  # Optional environment variables
)

async def run():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(
            read,
            write,
        ) as session:
            prompt = "I want to book an apartment in Paris for 2 nights. 03/28 - 03/30"
            # Initialize the connection
            await session.initialize()
            
            # Get tools from MCP session and convert to Gemini Tool objects
            mcp_tools = await session.list_tools()
            tools = types.Tool(function_declarations=[
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                }
                for tool in mcp_tools.tools
            ])
            
            # Send request with function declarations
            response = client.models.generate_content(
                model="gemini-2.0-flash",  # Or your preferred model supporting function calling
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    tools=[tools],
                ),  # Example other config
            )
        # Check for a function call
        if response.candidates[0].content.parts[0].function_call:
            function_call = response.candidates[0].content.parts[0].function_call
            print(f"Function to call: {function_call.name}")
            print(f"Arguments: {function_call.args}")
            # In a real app, you would call your function here:
            # result = await session.call_tool(function_call.args, arguments=function_call.args)
            # sent new request with function call
        else:
            print("No function call found in the response.")
            print(response.text)
            
if __name__ == "__main__":
    import asyncio
    asyncio.run(run())