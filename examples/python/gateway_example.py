"""
Gateway Example - Multi-Agent Coordination

This example demonstrates how to use the Gateway for coordinating
multiple agents and managing real-time communication.
"""

from praisonaiagents import Agent, GatewayConfig, SessionConfig

# Configure the gateway
from pydantic import BaseModel, Field

class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    drain_timeout: int = 30
    reload_drain_timeout: int = 60
    max_connections: int = 1000
    heartbeat_interval: int = 30

class GatewayConfig:
    def __init__(self, host="0.0.0.0", port=8000, drain_timeout=30, reload_drain_timeout=60, max_connections=1000, heartbeat_interval=30, session_config=None):
        self.host = host
        self.port = port
        self.drain_timeout = drain_timeout
        self.reload_drain_timeout = reload_drain_timeout
        self.max_connections = max_connections
        self.heartbeat_interval = heartbeat_interval
        self.session_config = session_config or SessionConfig()
        self.ws_url = f"ws://{self.host}:{self.port}"

gateway_config = GatewayConfig(
    host="127.0.0.1",
    port=8765,
    max_connections=100,
    heartbeat_interval=30,
    session_config=SessionConfig(
        timeout=3600,
        max_messages=500,
    )
)

# Create specialized agents
researcher = Agent(
    name="researcher",
    instructions="You research topics thoroughly and provide detailed information.",
    llm="gpt-4o-mini"
)

writer = Agent(
    name="writer",
    instructions="You write clear, engaging content based on research.",
    llm="gpt-4o-mini"
)

# Example: Simple agent interaction
if __name__ == "__main__":
    print("Gateway Configuration:")
    print(f"  Host: {gateway_config.host}")
    print(f"  Port: {gateway_config.port}")
    print(f"  WebSocket URL: {gateway_config.ws_url}")
    print(f"  Max Connections: {gateway_config.max_connections}")
    print()
    
    # Test agent
    response = researcher.start("What are the key benefits of multi-agent systems?")
    print("Researcher Response:")
    print(response)
