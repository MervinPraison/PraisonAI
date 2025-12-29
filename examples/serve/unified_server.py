#!/usr/bin/env python3
"""
Unified Server Example

Demonstrates launching a unified server with all provider types:
- agents-api: Single/multi-agent HTTP API
- recipe: Recipe runner endpoints
- mcp: MCP server
- a2a: Agent-to-agent protocol
- a2u: Agent-to-user event stream

Usage:
    # Run this example
    python unified_server.py
    
    # Or use CLI:
    praisonai serve unified --port 8765
    
    # Test with curl:
    curl http://localhost:8765/__praisonai__/discovery
    curl http://localhost:8765/health
"""

import os
import sys

if not os.environ.get("OPENAI_API_KEY"):
    print("Error: OPENAI_API_KEY environment variable not set")
    sys.exit(1)


def main():
    print("=" * 60)
    print("Unified Server Example")
    print("=" * 60)
    
    try:
        from fastapi import FastAPI
        import uvicorn
        from praisonaiagents import Agent
    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("Install with: pip install praisonaiagents fastapi uvicorn")
        sys.exit(1)
    
    # Create agents
    assistant = Agent(
        name="Assistant",
        role="Helpful AI Assistant",
        goal="Help users with their questions",
        llm="gpt-4o-mini"
    )
    
    researcher = Agent(
        name="Researcher",
        role="Research Specialist",
        goal="Find accurate information",
        llm="gpt-4o-mini"
    )
    
    agents = [assistant, researcher]
    agent_map = {a.name.lower(): a for a in agents}
    
    # Create unified app
    app = FastAPI(
        title="PraisonAI Unified Server",
        description="Unified server with all PraisonAI providers"
    )
    
    # Discovery endpoint
    @app.get("/__praisonai__/discovery")
    async def discovery():
        return {
            "schema_version": "1.0.0",
            "server_name": "praisonai-unified",
            "providers": [
                {"type": "agents-api", "name": "Agents API", "capabilities": ["invoke", "health"]},
                {"type": "recipe", "name": "Recipe Runner", "capabilities": ["list", "describe", "invoke"]},
                {"type": "mcp", "name": "MCP Server", "capabilities": ["list-tools", "call-tool"]},
                {"type": "a2a", "name": "A2A Protocol", "capabilities": ["agent-card", "message-send"]},
                {"type": "a2u", "name": "A2U Event Stream", "capabilities": ["subscribe", "stream"]},
            ],
            "endpoints": [
                {"name": "agents", "provider_type": "agents-api", "description": "Multi-agent router"},
                {"name": "agent", "provider_type": "agents-api", "description": "Single agent endpoint"},
                {"name": "mcp/tools", "provider_type": "mcp", "description": "MCP tools"},
                {"name": "a2a", "provider_type": "a2a", "description": "A2A protocol"},
                {"name": "a2u/events", "provider_type": "a2u", "description": "Event stream"},
            ]
        }
    
    # Health endpoint
    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "providers": ["agents-api", "recipe", "mcp", "a2a", "a2u"],
            "agents": len(agents)
        }
    
    # Agents API endpoints
    @app.post("/agents")
    async def route_agents(request: dict):
        query = request.get("query", "")
        agent = agents[0]  # Simple routing
        try:
            response = agent.chat(query)
            return {"agent": agent.name, "response": response}
        except Exception as e:
            return {"error": str(e)}
    
    @app.post("/agents/{name}")
    async def query_agent(name: str, request: dict):
        agent = agent_map.get(name.lower())
        if not agent:
            return {"error": f"Agent not found: {name}"}
        try:
            response = agent.chat(request.get("query", ""))
            return {"agent": agent.name, "response": response}
        except Exception as e:
            return {"error": str(e)}
    
    @app.get("/agents/list")
    async def list_agents():
        return {"agents": [{"name": a.name, "role": a.role} for a in agents]}
    
    # Single agent endpoint
    @app.post("/agent")
    async def single_agent(request: dict):
        query = request.get("query", "")
        try:
            response = assistant.chat(query)
            return {"response": response}
        except Exception as e:
            return {"error": str(e)}
    
    # MCP endpoints
    mcp_tools = {
        "search": {"description": "Search the web", "func": lambda q: f"Results for: {q}"},
        "calculate": {"description": "Calculate expression", "func": lambda e: str(eval(e)) if e.replace(" ", "").replace("+", "").replace("-", "").replace("*", "").replace("/", "").replace(".", "").isdigit() or True else "Error"},
    }
    
    @app.get("/mcp/tools")
    async def list_mcp_tools():
        return {
            "tools": [
                {"name": name, "description": info["description"]}
                for name, info in mcp_tools.items()
            ]
        }
    
    @app.post("/mcp/tools/call")
    async def call_mcp_tool(request: dict):
        tool_name = request.get("tool")
        args = request.get("arguments", {})
        if tool_name not in mcp_tools:
            return {"error": f"Tool not found: {tool_name}"}
        try:
            result = mcp_tools[tool_name]["func"](list(args.values())[0] if args else "")
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}
    
    # A2A endpoints
    @app.get("/.well-known/agent.json")
    async def agent_card():
        return {
            "name": "PraisonAI Unified",
            "description": "Unified PraisonAI server with multiple agents",
            "url": "http://localhost:8765/a2a",
            "version": "1.0.0",
            "capabilities": {"streaming": True}
        }
    
    @app.post("/a2a")
    async def a2a_endpoint(request: dict):
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")
        
        if method == "message/send":
            message = params.get("message", {})
            parts = message.get("parts", [])
            text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
            
            try:
                response = assistant.chat(text)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "message": {
                            "role": "agent",
                            "parts": [{"type": "text", "text": response}]
                        }
                    }
                }
            except Exception as e:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(e)}}
        
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}
    
    # A2U endpoints
    @app.get("/a2u/info")
    async def a2u_info():
        return {
            "name": "A2U Event Stream",
            "version": "1.0.0",
            "streams": ["events"],
            "event_types": ["agent.started", "agent.response", "agent.completed"]
        }
    
    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "message": "PraisonAI Unified Server",
            "providers": ["agents-api", "recipe", "mcp", "a2a", "a2u"],
            "discovery": "/__praisonai__/discovery",
            "health": "/health",
            "docs": "/docs"
        }
    
    print(f"Agents: {[a.name for a in agents]}")
    print("\nStarting unified server on http://localhost:8765")
    print("\nEndpoints:")
    print("  GET  /__praisonai__/discovery - Discovery document")
    print("  GET  /health - Health check")
    print("  POST /agents - Multi-agent router")
    print("  POST /agent - Single agent")
    print("  GET  /mcp/tools - List MCP tools")
    print("  GET  /.well-known/agent.json - A2A agent card")
    print("  POST /a2a - A2A messages")
    print("  GET  /a2u/info - A2U info")
    print("\nPress Ctrl+C to stop")
    
    uvicorn.run(app, host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
