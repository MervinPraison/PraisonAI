#!/usr/bin/env python3
"""
Tools as MCP Server Example

Demonstrates exposing Python tools as an MCP server:
- Register custom functions as MCP tools
- SSE transport for Claude Desktop/Cursor
- Stdio transport for local integration

Usage:
    # Run this example (SSE mode)
    python tools_as_mcp_server.py
    
    # Or use CLI:
    praisonai serve tools --port 8081
    
    # Test with curl:
    curl http://localhost:8081/sse
"""

import sys


def main():
    print("=" * 60)
    print("Tools as MCP Server Example")
    print("=" * 60)
    
    try:
        from praisonaiagents.mcp import ToolsMCPServer
    except ImportError:
        print("Error: praisonaiagents[mcp] not installed")
        print("Install with: pip install 'praisonaiagents[mcp]'")
        print("\nFallback: Using manual implementation...")
        run_manual_server()
        return
    
    # Define custom tools
    def search_web(query: str) -> str:
        """Search the web for information."""
        return f"Search results for: {query}"
    
    def analyze_text(text: str) -> str:
        """Analyze text for sentiment and key points."""
        word_count = len(text.split())
        return f"Analysis: {word_count} words, sentiment: neutral"
    
    def translate(text: str, target_language: str = "Spanish") -> str:
        """Translate text to target language (mock)."""
        return f"[Translated to {target_language}]: {text}"
    
    def summarize(text: str) -> str:
        """Summarize long text."""
        words = text.split()
        if len(words) > 20:
            return " ".join(words[:20]) + "..."
        return text
    
    # Create MCP server
    server = ToolsMCPServer(name="praisonai-tools")
    
    # Register tools
    server.register_tool(search_web)
    server.register_tool(analyze_text)
    server.register_tool(translate)
    server.register_tool(summarize)
    
    print(f"Registered tools: {[search_web.__name__, analyze_text.__name__, translate.__name__, summarize.__name__]}")
    print("\nStarting MCP server with SSE transport...")
    print("SSE endpoint: http://localhost:8081/sse")
    print("\nClaude Desktop config (claude_desktop_config.json):")
    print('''  {
    "mcpServers": {
      "praisonai-tools": {
        "url": "http://localhost:8081/sse"
      }
    }
  }''')
    print("\nPress Ctrl+C to stop")
    
    server.run(transport="sse", host="0.0.0.0", port=8081)


def run_manual_server():
    """Manual MCP server implementation as fallback."""
    try:
        from fastapi import FastAPI
        from fastapi.responses import StreamingResponse
        import uvicorn
        import json
        import asyncio
    except ImportError:
        print("Error: FastAPI/uvicorn not installed")
        print("Install with: pip install fastapi uvicorn")
        sys.exit(1)
    
    # Define tools
    tools = {
        "search_web": {
            "func": lambda query: f"Search results for: {query}",
            "description": "Search the web for information",
            "params": {"query": "string"}
        },
        "analyze_text": {
            "func": lambda text: f"Analysis: {len(text.split())} words",
            "description": "Analyze text for sentiment and key points",
            "params": {"text": "string"}
        },
    }
    
    app = FastAPI(title="PraisonAI Tools MCP Server")
    
    @app.get("/sse")
    async def sse_endpoint():
        """SSE endpoint for MCP."""
        async def event_stream():
            # Send initial tools list
            tools_list = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "result": {
                    "tools": [
                        {
                            "name": name,
                            "description": info["description"],
                            "inputSchema": {
                                "type": "object",
                                "properties": {k: {"type": v} for k, v in info["params"].items()},
                                "required": list(info["params"].keys())
                            }
                        }
                        for name, info in tools.items()
                    ]
                }
            }
            yield f"data: {json.dumps(tools_list)}\n\n"
            
            # Keep connection alive
            while True:
                await asyncio.sleep(30)
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    
    @app.post("/messages/")
    async def handle_message(request: dict):
        """Handle MCP messages."""
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")
        
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": name,
                            "description": info["description"],
                            "inputSchema": {
                                "type": "object",
                                "properties": {k: {"type": v} for k, v in info["params"].items()}
                            }
                        }
                        for name, info in tools.items()
                    ]
                }
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name not in tools:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Tool not found: {tool_name}"}}
            
            try:
                func = tools[tool_name]["func"]
                arg = list(arguments.values())[0] if arguments else ""
                result = func(arg)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": result}]}
                }
            except Exception as e:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(e)}}
        
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}
    
    @app.get("/__praisonai__/discovery")
    async def discovery():
        return {
            "schema_version": "1.0.0",
            "server_name": "praisonai-tools-mcp",
            "providers": [{"type": "tools-mcp", "name": "Tools MCP Server", "capabilities": ["list-tools", "call-tool"]}],
            "endpoints": [{"name": "tools", "provider_type": "tools-mcp"}]
        }
    
    @app.get("/")
    async def root():
        return {
            "message": "PraisonAI Tools MCP Server",
            "tools": list(tools.keys()),
            "sse": "/sse",
            "messages": "/messages/"
        }
    
    print(f"Tools: {list(tools.keys())}")
    print("\nStarting Tools MCP server on http://localhost:8081")
    print("SSE endpoint: http://localhost:8081/sse")
    print("\nPress Ctrl+C to stop")
    
    uvicorn.run(app, host="127.0.0.1", port=8081)


if __name__ == "__main__":
    main()
