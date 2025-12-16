"""MCP Tools Server with SSE Transport

Expose Python functions as MCP tools via Server-Sent Events (SSE).
This is useful for web-based clients and remote access.

Usage:
    python mcp-tools-server-sse.py
    
    # Then connect from another agent:
    # agent = Agent(tools=MCP("http://localhost:8080/sse"))
"""

from praisonaiagents.mcp import ToolsMCPServer


def search_web(query: str, max_results: int = 5) -> dict:
    """Search the web for information.
    
    Args:
        query: The search query
        max_results: Maximum results to return
    """
    return {
        "query": query,
        "results": [
            {"title": f"Result {i+1}", "url": f"https://example.com/{i+1}"}
            for i in range(max_results)
        ]
    }


def calculate(expression: str) -> dict:
    """Evaluate a mathematical expression.
    
    Args:
        expression: Math expression (e.g., "2 + 2 * 3")
    """
    try:
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expression):
            return {"error": "Invalid characters"}
        return {"expression": expression, "result": eval(expression)}
    except Exception as e:
        return {"error": str(e)}


def get_time() -> dict:
    """Get the current time."""
    from datetime import datetime
    now = datetime.now()
    return {
        "time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": now.isoformat()
    }


if __name__ == "__main__":
    server = ToolsMCPServer(name="sse-tools-server")
    server.register_tools([search_web, calculate, get_time])
    
    print("Starting SSE MCP Server...")
    print("Connect with: MCP('http://localhost:8080/sse')")
    
    server.run_sse(host="0.0.0.0", port=8080)
