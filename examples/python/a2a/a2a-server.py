"""
PraisonAI A2A Server Example

Expose a PraisonAI Agent as an A2A (Agent2Agent) Server.
This enables other AI agents to discover and communicate with your agent.

Run:
    uvicorn a2a-server:app --reload

Endpoints:
    GET /.well-known/agent.json  - Agent Card for discovery
    GET /status                   - Server status
"""

from praisonaiagents import Agent, A2A
from fastapi import FastAPI

# Create an agent with tools
def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Search results for: {query}"

def calculate(expression: str) -> str:
    """Calculate a mathematical expression."""
    try:
        return f"Result: {eval(expression)}"
    except Exception:
        return "Invalid expression"

agent = Agent(
    name="Research Assistant",
    role="Research Analyst",
    goal="Help users research topics and answer questions",
    tools=[search_web, calculate]
)

# Expose as A2A Server
a2a = A2A(
    agent=agent,
    url="http://localhost:8000/a2a",
    version="1.0.0"
)

# Create FastAPI app
app = FastAPI(
    title="PraisonAI A2A Server",
    description="A2A-compatible agent server"
)
app.include_router(a2a.get_router())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
