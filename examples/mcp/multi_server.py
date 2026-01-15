"""
Multi-Server MCP Example.

This example demonstrates how to use multiple MCP servers with PraisonAI Agents,
including mixing MCP tools with regular Python function tools.

Requirements:
    - Node.js and npx installed (or uvx for Python-based servers)
    - pip install praisonaiagents[mcp]
    - OPENAI_API_KEY environment variable set

Usage:
    python multi_server.py
"""

from praisonaiagents import Agent, MCP
import os


def calculate(expression: str) -> str:
    """
    A simple calculator tool that evaluates mathematical expressions.
    
    Args:
        expression: A mathematical expression to evaluate (e.g., "2 + 2")
    
    Returns:
        The result of the calculation
    """
    try:
        # Safe evaluation of mathematical expressions
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return "Error: Invalid characters in expression"
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


def main():
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Please set OPENAI_API_KEY environment variable")
        return
    
    print("=" * 60)
    print("Multi-Server MCP Example")
    print("=" * 60)
    
    # Create MCP instance with Time server
    print("\nInitializing MCP servers...")
    try:
        time_mcp = MCP("uvx mcp-server-time", timeout=30)
        print("✓ Time MCP server initialized")
    except Exception as e:
        print(f"✗ Time MCP server failed: {e}")
        return
    
    # Create an agent with multiple tool sources
    agent = Agent(
        name="MultiToolAgent",
        instructions="""You are a helpful assistant with access to multiple tools:
        1. Time tools - for getting current time in different timezones
        2. Calculator - for mathematical calculations
        
        Use the appropriate tool based on the user's request.""",
        llm="openai/gpt-4o-mini",
        tools=[time_mcp, calculate]  # Mix MCP and regular tools
    )
    
    # Show available tools
    print("\nAvailable tools:")
    formatted_tools = agent._format_tools_for_completion(agent.tools)
    for tool in formatted_tools:
        print(f"  - {tool['function']['name']}: {tool['function']['description'][:50]}...")
    
    # Example queries
    queries = [
        "What time is it in Tokyo?",
        "Calculate 15 * 7 + 23",
        "What's the current time in New York and London?"
    ]
    
    print("\n" + "=" * 60)
    print("Running queries...")
    print("=" * 60)
    
    for i, query in enumerate(queries, 1):
        print(f"\n--- Query {i} ---")
        print(f"Question: {query}\n")
        
        try:
            response = agent.chat(query)
            print(f"Response:\n{response}")
        except Exception as e:
            print(f"Error: {e}")
        
        print("-" * 40)
    
    # Clean up
    time_mcp.shutdown()
    print("\nDone!")


def demo_multiple_mcp_servers():
    """
    Demonstrate using multiple MCP servers simultaneously.
    
    This function shows how to create agents with multiple MCP servers,
    each providing different capabilities.
    """
    print("\n" + "=" * 60)
    print("Multiple MCP Servers Demo")
    print("=" * 60)
    
    # Initialize multiple MCP servers
    servers = {}
    
    try:
        servers['time'] = MCP("uvx mcp-server-time", timeout=30)
        print("✓ Time server initialized")
    except Exception as e:
        print(f"✗ Time server failed: {e}")
    
    # Create agent with all available servers
    available_tools = list(servers.values())
    
    if not available_tools:
        print("No MCP servers available")
        return
    
    agent = Agent(
        name="MultiServerAgent",
        instructions="You have access to multiple MCP servers. Use the appropriate tools.",
        llm="openai/gpt-4o-mini",
        tools=available_tools
    )
    
    print(f"\nAgent created with {len(available_tools)} MCP server(s)")
    
    # Clean up
    for server in servers.values():
        server.shutdown()


if __name__ == "__main__":
    main()
