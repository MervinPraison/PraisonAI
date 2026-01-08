#!/usr/bin/env python3
"""
Multi-Agent Router as HTTP API Example

Demonstrates launching multiple agents as an HTTP API with:
- Router endpoint for automatic agent selection
- Per-agent endpoints
- Streaming support (SSE)
- Discovery endpoint

Usage:
    # Run this example
    python agents_as_api_router.py
    
    # Or use CLI:
    praisonai serve agents --file agents.yaml --port 8000
    
    # Test with curl:
    curl -X POST http://localhost:8000/agents \
      -H "Content-Type: application/json" \
      -d '{"query": "Research AI trends"}'
"""

import os
import sys

if not os.environ.get("OPENAI_API_KEY"):
    print("Error: OPENAI_API_KEY environment variable not set")
    sys.exit(1)


def main():
    print("=" * 60)
    print("Multi-Agent Router as HTTP API Example")
    print("=" * 60)
    
    try:
        from praisonaiagents import Agent, Agents
    except ImportError:
        print("Error: praisonaiagents not installed")
        print("Install with: pip install praisonaiagents")
        sys.exit(1)
    
    # Create multiple agents
    researcher = Agent(
        name="Researcher",
        role="Research Specialist",
        goal="Find accurate and relevant information",
        backstory="Expert at finding and synthesizing information from various sources.",
        llm="gpt-4o-mini"
    )
    
    writer = Agent(
        name="Writer",
        role="Content Writer",
        goal="Create engaging content from research",
        backstory="Skilled writer who transforms research into readable content.",
        llm="gpt-4o-mini"
    )
    
    analyst = Agent(
        name="Analyst",
        role="Data Analyst",
        goal="Analyze data and provide insights",
        backstory="Expert at analyzing data and extracting meaningful insights.",
        llm="gpt-4o-mini"
    )
    
    agents = [researcher, writer, analyst]
    
    print(f"Agents: {[a.name for a in agents]}")
    
    # Create multi-agent system
    praison = Agents(agents=agents)
    
    print("\nLaunching multi-agent router as HTTP API...")
    print("Endpoints:")
    print("  POST /agents - Route to best agent")
    print("  POST /agents/researcher - Query researcher")
    print("  POST /agents/writer - Query writer")
    print("  POST /agents/analyst - Query analyst")
    print("  GET  /agents/list - List all agents")
    print("  GET  /health - Health check")
    print("  GET  /__praisonai__/discovery - Discovery document")
    print("\nPress Ctrl+C to stop")
    
    try:
        # Use Agents.launch() to start HTTP server
        praison.launch(
            port=8000,
            host="127.0.0.1"
        )
    except KeyboardInterrupt:
        print("\nServer stopped")
    except Exception as e:
        print(f"Error launching server: {e}")
        print("\nFallback: Using manual FastAPI setup...")
        launch_manual(agents)


def launch_manual(agents):
    """Manual FastAPI server setup as fallback."""
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        import uvicorn
    except ImportError:
        print("Error: FastAPI/uvicorn not installed")
        print("Install with: pip install fastapi uvicorn")
        return
    
    app = FastAPI(title="PraisonAI Multi-Agent API")
    
    # Create agent lookup
    agent_map = {a.name.lower(): a for a in agents}
    
    @app.post("/agents")
    async def route_query(request: Request):
        """Route query to best agent."""
        try:
            body = await request.json()
            query = body.get("query", "")
            if not query:
                return JSONResponse({"error": "query required"}, status_code=400)
            
            # Simple routing based on keywords
            query_lower = query.lower()
            if any(w in query_lower for w in ["research", "find", "search"]):
                agent = agent_map.get("researcher", agents[0])
            elif any(w in query_lower for w in ["write", "create", "draft"]):
                agent = agent_map.get("writer", agents[0])
            elif any(w in query_lower for w in ["analyze", "data", "insight"]):
                agent = agent_map.get("analyst", agents[0])
            else:
                agent = agents[0]
            
            response = agent.chat(query)
            return {"agent": agent.name, "response": response}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    
    @app.post("/agents/{agent_name}")
    async def query_agent(agent_name: str, request: Request):
        """Query specific agent."""
        agent = agent_map.get(agent_name.lower())
        if not agent:
            return JSONResponse({"error": f"Agent not found: {agent_name}"}, status_code=404)
        
        try:
            body = await request.json()
            query = body.get("query", "")
            response = agent.chat(query)
            return {"agent": agent.name, "response": response}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    
    @app.get("/agents/list")
    async def list_agents():
        return {"agents": [{"name": a.name, "role": a.role} for a in agents]}
    
    @app.get("/health")
    async def health():
        return {"status": "healthy", "agents": len(agents)}
    
    @app.get("/__praisonai__/discovery")
    async def discovery():
        return {
            "schema_version": "1.0.0",
            "server_name": "praisonai-agents-router",
            "providers": [{"type": "agents-api", "name": "Multi-Agent Router"}],
            "endpoints": [
                {"name": "agents", "provider_type": "agents-api"},
                *[{"name": f"agents/{a.name.lower()}", "provider_type": "agents-api"} for a in agents]
            ]
        }
    
    @app.get("/")
    async def root():
        return {
            "message": "PraisonAI Multi-Agent Router",
            "agents": [a.name for a in agents],
            "endpoints": ["/agents", "/agents/list", "/health"]
        }
    
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
