#!/usr/bin/env python3
"""
Custom Tools MCP Server Example

Register custom tools and expose them via MCP server.

Usage:
    python custom_tools_server.py
"""


def main():
    """Run MCP server with custom tools."""
    from praisonai.mcp_server.server import MCPServer
    from praisonai.mcp_server.registry import register_tool, get_tool_registry
    
    # Register custom tools
    @register_tool("custom.greet")
    def greet(name: str) -> str:
        """Greet a person by name."""
        return f"Hello, {name}! Welcome to PraisonAI."
    
    @register_tool("custom.calculate")
    def calculate(expression: str) -> str:
        """Safely evaluate a mathematical expression."""
        try:
            # Only allow safe math operations
            allowed = set("0123456789+-*/.(). ")
            if not all(c in allowed for c in expression):
                return "Error: Invalid characters in expression"
            result = eval(expression)  # Safe due to character filtering
            return f"Result: {result}"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("custom.reverse")
    def reverse_text(text: str) -> str:
        """Reverse a text string."""
        return text[::-1]
    
    @register_tool("custom.word_count")
    def word_count(text: str) -> str:
        """Count words in text."""
        words = text.split()
        return f"Word count: {len(words)}"
    
    # Show registered tools
    registry = get_tool_registry()
    tools = registry.list_all()
    print(f"Registered {len(tools)} custom tools:")
    for tool in tools:
        print(f"  - {tool.name}: {tool.description}")
    print()
    
    # Create and run server
    server = MCPServer(
        name="praisonai-custom",
        version="1.0.0",
        instructions="Custom tools MCP server example.",
    )
    
    print("Starting MCP server on http://127.0.0.1:8080/mcp")
    server.run(
        transport="http-stream",
        host="127.0.0.1",
        port=8080,
    )


if __name__ == "__main__":
    main()
