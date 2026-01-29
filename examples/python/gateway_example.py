"""
Gateway Example - Multi-Agent Coordination

This example demonstrates how to use the Gateway for coordinating
multiple agents and managing real-time communication.
"""

from praisonaiagents import Agent, GatewayConfig, SessionConfig

# Configure the gateway
gateway_config = GatewayConfig(
    host="127.0.0.1",
    port=8765,
    max_connections=100,
    heartbeat_interval=30,
    session_config=SessionConfig(
        timeout=3600,  # 1 hour session timeout
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
