"""
MCP Client using the MCPWrapper to interact with MCP servers.

This script demonstrates how to use the MCPWrapper to connect to an MCP server
and execute queries using Google's Gemini models.
"""

import os
import asyncio
import argparse
from dotenv import load_dotenv

from mcp_wrapper import MCPWrapper

# Load environment variables from .env file if it exists
load_dotenv()

async def main():
    parser = argparse.ArgumentParser(description='MCP Client for Gemini')
    parser.add_argument('--api-key', help='Google API key for Gemini')
    parser.add_argument('--model', default='gemini-1.5-pro', help='Model to use (default: gemini-1.5-pro)')
    args = parser.parse_args()
    
    # Get API key from args or environment
    api_key = args.api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: API key must be provided via --api-key or GEMINI_API_KEY environment variable")
        return
    
    # Create the MCP wrapper
    wrapper = MCPWrapper(api_key=api_key, model=args.model)
    
    try:
        # Connect to the test MCP server
        print("Connecting to test MCP server...")
        await wrapper.connect_to_server(
            command="python",
            args=[
                "/Users/praison/praisonai-package/src/praisonai-agents/mcp_test_server.py",
            ]
        )
        
        # Interactive mode
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            query = input("\nQuery: ").strip()
            
            if query.lower() == 'quit':
                break
            
            print("Processing query...")
            response = await wrapper.execute_query(query)
            print("\nResponse:")
            print(response.text)
    
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        # Close the session
        if wrapper.session:
            await wrapper.close()
            print("Session closed.")

if __name__ == "__main__":
    asyncio.run(main())
