#!/usr/bin/env python3
"""
MCP HTTP Server Example

Demonstrates launching an MCP server with HTTP transport:
- HTTP-based MCP protocol
- Tool registration
- Discovery endpoint

Usage:
    # Run this example
    python mcp_http_server.py
    
    # Or use CLI:
    praisonai serve mcp --transport http --port 8080
    
    # Test with curl:
    curl http://localhost:8080/mcp/tools
    curl -X POST http://localhost:8080/mcp/tools/call \
      -H "Content-Type: application/json" \
      -d '{"tool": "search", "arguments": {"query": "AI news"}}'
"""

import sys


def main():
    print("=" * 60)
    print("MCP HTTP Server Example")
    print("=" * 60)
    
    try:
        from fastapi import FastAPI
        import uvicorn
    except ImportError:
        print("Error: FastAPI/uvicorn not installed")
        print("Install with: pip install fastapi uvicorn")
        sys.exit(1)
    
    # Define tools
    def search(query: str) -> str:
        """Search the web for information."""
        return f"Search results for: {query}"
    
    def calculate(expression: str) -> str:
        """Calculate a math expression safely."""
        try:
            # Safe eval for basic math
            allowed = set("0123456789+-*/.() ")
            if all(c in allowed for c in expression):
                return str(eval(expression))
            return "Error: Invalid expression"
        except Exception as e:
            return f"Error: {e}"
    
    def get_weather(city: str) -> str:
        """Get weather for a city (mock)."""
        return f"Weather in {city}: Sunny, 72°F"
    
    tools = {
        "search": {"func": search, "description": "Search the web for information"},
        "calculate": {"func": calculate, "description": "Calculate a math expression"},
        "get_weather": {"func": get_weather, "description": "Get weather for a city"},
    }
    
    app = FastAPI(title="PraisonAI MCP Server")
    
    @app.get("/mcp/tools")
    async def list_tools():
        """List available MCP tools."""
        return {
            "tools": [
                {
                    "name": name,
                    "description": info["description"],
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            list(info["func"].__code__.co_varnames)[0]: {"type": "string"}
                        },
                        "required": [list(info["func"].__code__.co_varnames)[0]]
                    }
                }
                for name, info in tools.items()
            ]
        }
    
    @app.post("/mcp/tools/call")
    async def call_tool(request: dict):
        """Call an MCP tool."""
        tool_name = request.get("tool")
        arguments = request.get("arguments", {})
        
        if tool_name not in tools:
            return {"error": f"Tool not found: {tool_name}"}
        
        try:
            func = tools[tool_name]["func"]
            # Get first argument
            arg_name = list(func.__code__.co_varnames)[0]
            arg_value = arguments.get(arg_name, "")
            result = func(arg_value)
            return {"result": result, "tool": tool_name}
        except Exception as e:
            return {"error": str(e)}
    
    @app.get("/__praisonai__/discovery")
    async def discovery():
        return {
            "schema_version": "1.0.0",
            "server_name": "praisonai-mcp",
            "providers": [{"type": "mcp", "name": "MCP Server", "capabilities": ["list-tools", "call-tool"]}],
            "endpoints": [{"name": "mcp", "provider_type": "mcp"}]
        }
    
    @app.get("/health")
    async def health():
        return {"status": "healthy", "tools": len(tools)}
    
    @app.get("/")
    async def root():
        return {
            "message": "PraisonAI MCP Server (HTTP)",
            "tools": list(tools.keys()),
            "endpoints": ["/mcp/tools", "/mcp/tools/call", "/health"]
        }
    
    print(f"Tools: {list(tools.keys())}")
    print("\nStarting MCP HTTP server on http://localhost:8080")
    print("List tools: GET http://localhost:8080/mcp/tools")
    print("Call tool: POST http://localhost:8080/mcp/tools/call")
    print("\nPress Ctrl+C to stop")
    
    uvicorn.run(app, host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
