# praisonai: skip=true
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
            import ast, operator
            _OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
                    ast.Mod: operator.mod, ast.Pow: operator.pow,
                    ast.USub: operator.neg, ast.UAdd: operator.pos}
            def _ev(n):
                if isinstance(n, ast.Expression): return _ev(n.body)
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return n.value
                if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS: return _OPS[type(n.op)](_ev(n.operand))
                if isinstance(n, ast.BinOp) and type(n.op) in _OPS: return _OPS[type(n.op)](_ev(n.left), _ev(n.right))
                raise ValueError(f"Unsupported: {ast.dump(n)}")
            return f"Result: {_ev(ast.parse(expression, mode='eval'))}"
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
