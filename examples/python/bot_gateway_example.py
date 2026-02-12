"""
Bot Gateway Example — Run multiple bots from one gateway server.

This example shows how to start a multi-bot gateway that connects
Telegram, Discord, and Slack bots to different AI agents.

Usage:
    1. Set environment variables:
        export OPENAI_API_KEY=your_key
        export TELEGRAM_BOT_TOKEN=your_token

    2. Run:
        python bot_gateway_example.py
"""

import asyncio
from praisonai.gateway import WebSocketGateway
from praisonaiagents import Agent
from praisonaiagents.gateway import GatewayConfig

# Create agents
personal = Agent(name="personal", instructions="You are a helpful personal assistant")
support = Agent(name="support", instructions="You are a customer support agent")

# Create gateway
config = GatewayConfig(host="127.0.0.1", port=8765)
gateway = WebSocketGateway(config=config)

# Register agents
gateway.register_agent(personal, agent_id="personal")
gateway.register_agent(support, agent_id="support")

# Start gateway (WebSocket server + health endpoint)
if __name__ == "__main__":
    print("Starting gateway on ws://127.0.0.1:8765")
    print("Health check: http://127.0.0.1:8765/health")
    asyncio.run(gateway.start())
