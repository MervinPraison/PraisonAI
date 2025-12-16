"""MCP Tools Server Example

Expose Python functions as MCP tools for external clients like Claude Desktop, Cursor, etc.

Usage:
    # Run as stdio server (for Claude Desktop)
    python mcp-tools-server.py
    
    # Run as SSE server (for web clients)
    python mcp-tools-server.py --sse --port 8080
"""

import argparse
from typing import List, Dict, Any


# Define your custom tools as regular Python functions
# Type hints and docstrings are used to generate MCP schemas

def search_web(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Search the web for information.
    
    Args:
        query: The search query string
        max_results: Maximum number of results to return (default: 5)
    
    Returns:
        Search results with titles and URLs
    """
    # Mock implementation - replace with actual search logic
    return {
        "query": query,
        "results": [
            {"title": f"Result {i+1} for '{query}'", "url": f"https://example.com/{i+1}"}
            for i in range(max_results)
        ]
    }


def calculate(expression: str) -> Dict[str, Any]:
    """Evaluate a mathematical expression.
    
    Args:
        expression: A mathematical expression to evaluate (e.g., "2 + 2 * 3")
    
    Returns:
        The result of the calculation
    """
    try:
        # Safe evaluation of mathematical expressions
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return {"error": "Invalid characters in expression"}
        
        result = eval(expression)  # Use safer alternative in production
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}


def get_weather(city: str, units: str = "celsius") -> Dict[str, Any]:
    """Get current weather for a city.
    
    Args:
        city: Name of the city
        units: Temperature units - "celsius" or "fahrenheit" (default: celsius)
    
    Returns:
        Weather information for the city
    """
    # Mock implementation - replace with actual weather API
    return {
        "city": city,
        "temperature": 22 if units == "celsius" else 72,
        "units": units,
        "condition": "Sunny",
        "humidity": 45
    }


def list_files(directory: str = ".", pattern: str = "*") -> List[str]:
    """List files in a directory.
    
    Args:
        directory: Directory path to list (default: current directory)
        pattern: Glob pattern to filter files (default: *)
    
    Returns:
        List of file names matching the pattern
    """
    import glob
    import os
    
    try:
        full_pattern = os.path.join(directory, pattern)
        files = glob.glob(full_pattern)
        return [os.path.basename(f) for f in files]
    except Exception as e:
        return [f"Error: {str(e)}"]


def main():
    parser = argparse.ArgumentParser(description="Run PraisonAI Tools as MCP Server")
    parser.add_argument("--sse", action="store_true", help="Use SSE transport instead of stdio")
    parser.add_argument("--port", type=int, default=8080, help="Port for SSE server (default: 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host for SSE server")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    
    from praisonaiagents.mcp import ToolsMCPServer
    
    # Create server with custom name
    server = ToolsMCPServer(
        name="praisonai-custom-tools",
        debug=args.debug
    )
    
    # Register all tools
    server.register_tools([
        search_web,
        calculate,
        get_weather,
        list_files
    ])
    
    # Print registered tools
    print(f"📦 Registered {len(server.tools)} tools:")
    for name in server.get_tool_names():
        print(f"   - {name}")
    print()
    
    # Run the server
    if args.sse:
        server.run_sse(host=args.host, port=args.port)
    else:
        server.run_stdio()


if __name__ == "__main__":
    main()
