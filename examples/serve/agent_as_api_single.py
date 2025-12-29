#!/usr/bin/env python3
"""
Single Agent as HTTP API Example

Demonstrates launching a single agent as an HTTP API server with:
- REST endpoint for queries
- Streaming support (SSE)
- Discovery endpoint
- Health check

Usage:
    # Run this example
    python agent_as_api_single.py
    
    # Or use CLI:
    praisonai serve agents --file agents.yaml --port 8000
    
    # Test with curl:
    curl -X POST http://localhost:8000/agent \
      -H "Content-Type: application/json" \
      -d '{"query": "What is AI?"}'
"""

import os
import sys

# Ensure API key is set
if not os.environ.get("OPENAI_API_KEY"):
    print("Error: OPENAI_API_KEY environment variable not set")
    sys.exit(1)


def main():
    print("=" * 60)
    print("Single Agent as HTTP API Example")
    print("=" * 60)
    
    try:
        from praisonaiagents import Agent
    except ImportError:
        print("Error: praisonaiagents not installed")
        print("Install with: pip install praisonaiagents")
        sys.exit(1)
    
    # Create a single agent
    agent = Agent(
        name="Assistant",
        role="Helpful AI Assistant",
        goal="Help users with their questions accurately and concisely",
        backstory="You are a knowledgeable assistant who provides clear, helpful answers.",
        llm="gpt-4o-mini",
        verbose=True
    )
    
    print(f"Agent: {agent.name}")
    print(f"Role: {agent.role}")
    
    # Launch as HTTP API
    print("\nLaunching agent as HTTP API...")
    print("Endpoints:")
    print("  POST /agent - Query the agent")
    print("  GET  /health - Health check")
    print("  GET  /__praisonai__/discovery - Discovery document")
    print("\nPress Ctrl+C to stop")
    
    try:
        # Use Agent.launch() to start HTTP server
        agent.launch(
            port=8000,
            host="127.0.0.1",
            path="/agent"
        )
    except KeyboardInterrupt:
        print("\nServer stopped")
    except Exception as e:
        print(f"Error launching server: {e}")
        # Fallback: manual FastAPI setup
        print("\nFallback: Using manual FastAPI setup...")
        launch_manual(agent)


def launch_manual(agent):
    """Manual FastAPI server setup as fallback."""
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        import uvicorn
    except ImportError:
        print("Error: FastAPI/uvicorn not installed")
        print("Install with: pip install fastapi uvicorn")
        return
    
    app = FastAPI(title="PraisonAI Agent API")
    
    @app.post("/agent")
    async def query_agent(request: Request):
        try:
            body = await request.json()
            query = body.get("query", "")
            if not query:
                return JSONResponse({"error": "query required"}, status_code=400)
            
            response = agent.chat(query)
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
            "server_name": "praisonai-agent",
            "providers": [{"type": "agents-api", "name": "Single Agent API"}],
            "endpoints": [{"name": "agent", "provider_type": "agents-api"}]
        }
    
    @app.get("/")
    async def root():
        return {
            "message": f"PraisonAI Agent: {agent.name}",
            "endpoints": ["/agent", "/health", "/__praisonai__/discovery"]
        }
    
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
