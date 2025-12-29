#!/usr/bin/env python3
"""
Agent.launch() and Agents.launch() Example

Demonstrates the high-level Python API for launching servers:
- Agent.launch() for single agent
- Agents.launch() for multi-agent
- Different server modes (HTTP, MCP, A2A)

Usage:
    # Run this example
    python agent_launch_modes.py
    
    # Test endpoints:
    curl http://localhost:8000/agent
    curl http://localhost:8000/health
"""

import os
import sys

if not os.environ.get("OPENAI_API_KEY"):
    print("Error: OPENAI_API_KEY environment variable not set")
    sys.exit(1)


def demo_single_agent_launch():
    """Demo Agent.launch() for single agent."""
    print("\n--- Single Agent Launch ---")
    
    try:
        from praisonaiagents import Agent
    except ImportError:
        print("Error: praisonaiagents not installed")
        return False
    
    agent = Agent(
        name="Assistant",
        role="Helpful AI Assistant",
        goal="Help users with their questions",
        llm="gpt-4o-mini"
    )
    
    print(f"Agent: {agent.name}")
    print("Launching as HTTP API on port 8000...")
    print("\nEndpoints:")
    print("  POST /agent - Query the agent")
    print("  GET  /health - Health check")
    print("\nPress Ctrl+C to stop")
    
    try:
        agent.launch(port=8000, host="127.0.0.1", path="/agent")
    except AttributeError:
        print("Agent.launch() not available, using fallback...")
        launch_single_fallback(agent)
    except KeyboardInterrupt:
        print("\nStopped")
    
    return True


def demo_multi_agent_launch():
    """Demo Agents.launch() for multi-agent."""
    print("\n--- Multi-Agent Launch ---")
    
    try:
        from praisonaiagents import Agent, PraisonAIAgents
    except ImportError:
        print("Error: praisonaiagents not installed")
        return False
    
    researcher = Agent(
        name="Researcher",
        role="Research Specialist",
        goal="Find accurate information",
        llm="gpt-4o-mini"
    )
    
    writer = Agent(
        name="Writer",
        role="Content Writer",
        goal="Create engaging content",
        llm="gpt-4o-mini"
    )
    
    agents = PraisonAIAgents(agents=[researcher, writer])
    
    print(f"Agents: {[researcher.name, writer.name]}")
    print("Launching as HTTP API on port 8000...")
    print("\nEndpoints:")
    print("  POST /agents - Route to best agent")
    print("  POST /agents/researcher - Query researcher")
    print("  POST /agents/writer - Query writer")
    print("  GET  /agents/list - List agents")
    print("\nPress Ctrl+C to stop")
    
    try:
        agents.launch(port=8000, host="127.0.0.1")
    except AttributeError:
        print("Agents.launch() not available, using fallback...")
        launch_multi_fallback([researcher, writer])
    except KeyboardInterrupt:
        print("\nStopped")
    
    return True


def launch_single_fallback(agent):
    """Fallback implementation for Agent.launch()."""
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        import uvicorn
    except ImportError:
        print("Error: FastAPI/uvicorn not installed")
        return
    
    app = FastAPI(title=f"PraisonAI Agent: {agent.name}")
    
    @app.post("/agent")
    async def query(request: Request):
        try:
            body = await request.json()
            query_text = body.get("query", "")
            response = agent.chat(query_text)
            return {"response": response}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    
    @app.get("/health")
    async def health():
        return {"status": "healthy", "agent": agent.name}
    
    @app.get("/__praisonai__/discovery")
    async def discovery():
        return {
            "schema_version": "1.0.0",
            "server_name": f"praisonai-{agent.name.lower()}",
            "providers": [{"type": "agents-api", "name": "Single Agent API"}],
            "endpoints": [{"name": "agent", "provider_type": "agents-api"}]
        }
    
    uvicorn.run(app, host="127.0.0.1", port=8000)


def launch_multi_fallback(agents):
    """Fallback implementation for Agents.launch()."""
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        import uvicorn
    except ImportError:
        print("Error: FastAPI/uvicorn not installed")
        return
    
    app = FastAPI(title="PraisonAI Multi-Agent API")
    agent_map = {a.name.lower(): a for a in agents}
    
    @app.post("/agents")
    async def route(request: Request):
        try:
            body = await request.json()
            query_text = body.get("query", "")
            # Simple routing
            agent = agents[0]
            response = agent.chat(query_text)
            return {"agent": agent.name, "response": response}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    
    @app.post("/agents/{name}")
    async def query_agent(name: str, request: Request):
        agent = agent_map.get(name.lower())
        if not agent:
            return JSONResponse({"error": f"Agent not found: {name}"}, status_code=404)
        try:
            body = await request.json()
            response = agent.chat(body.get("query", ""))
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
            "server_name": "praisonai-agents",
            "providers": [{"type": "agents-api", "name": "Multi-Agent API"}],
            "endpoints": [
                {"name": "agents", "provider_type": "agents-api"},
                *[{"name": f"agents/{a.name.lower()}", "provider_type": "agents-api"} for a in agents]
            ]
        }
    
    uvicorn.run(app, host="127.0.0.1", port=8000)


def main():
    print("=" * 60)
    print("Agent.launch() and Agents.launch() Example")
    print("=" * 60)
    
    mode = sys.argv[1] if len(sys.argv) > 1 else "single"
    
    if mode == "multi":
        demo_multi_agent_launch()
    else:
        demo_single_agent_launch()


if __name__ == "__main__":
    main()
