"""
Multiple MCP Servers Example

This example demonstrates how to use multiple MCP servers with a single agent.
You can combine different MCP servers (time, memory, filesystem, etc.) along
with regular Python functions as tools.

Requirements:
- pip install praisonaiagents
- uvx (for mcp-server-time)
- npx (for @modelcontextprotocol servers)
"""

from praisonaiagents import Agent
from praisonaiagents.mcp import MCP


def my_custom_tool(query: str) -> str:
    """
    A custom Python function that can be used alongside MCP tools.
    
    Args:
        query: The search query
        
    Returns:
        A formatted result string
    """
    return f"Custom tool result for: {query}"


def main():
    # Example 1: Single MCP server (basic usage)
    print("=" * 60)
    print("Example 1: Single MCP Server")
    print("=" * 60)
    
    agent_single = Agent(
        name="TimeAgent",
        instructions="You are a helpful assistant that can tell time.",
        tools=MCP("uvx mcp-server-time")
    )
    
    response = agent_single.start("What time is it in Tokyo?")
    print(f"Response: {response}\n")
    
    # Example 2: Multiple MCP servers
    print("=" * 60)
    print("Example 2: Multiple MCP Servers")
    print("=" * 60)
    
    agent_multi = Agent(
        name="MultiMCPAgent",
        instructions="""You are a helpful assistant with access to multiple tools:
        - Time tools for getting current time and converting timezones
        - Memory tools for storing and retrieving information
        Use the appropriate tool based on the user's request.""",
        tools=[
            MCP("uvx mcp-server-time"),                     # Time tools
            MCP("npx @modelcontextprotocol/server-memory"), # Memory tools
        ]
    )
    
    response = agent_multi.start("What time is it in New York and London?")
    print(f"Response: {response}\n")
    
    # Example 3: Multiple MCP servers + custom functions
    print("=" * 60)
    print("Example 3: MCP Servers + Custom Functions")
    print("=" * 60)
    
    agent_mixed = Agent(
        name="MixedToolsAgent",
        instructions="""You are a helpful assistant with access to:
        - Time tools for timezone operations
        - A custom search tool for general queries
        Choose the right tool for each task.""",
        tools=[
            MCP("uvx mcp-server-time"),  # MCP server
            my_custom_tool                # Regular Python function
        ]
    )
    
    response = agent_mixed.start("What time is it in Paris?")
    print(f"Response: {response}\n")
    
    # Example 4: MCP with environment variables
    print("=" * 60)
    print("Example 4: MCP with Environment Variables")
    print("=" * 60)
    
    # Note: Replace with your actual API key
    # agent_with_env = Agent(
    #     name="SearchAgent",
    #     instructions="You can search the web for information.",
    #     tools=[
    #         MCP(
    #             command="npx",
    #             args=["-y", "@modelcontextprotocol/server-brave-search"],
    #             env={"BRAVE_API_KEY": "your-api-key-here"}
    #         ),
    #         MCP("uvx mcp-server-time")
    #     ]
    # )
    print("(Skipped - requires BRAVE_API_KEY)")


if __name__ == "__main__":
    main()
