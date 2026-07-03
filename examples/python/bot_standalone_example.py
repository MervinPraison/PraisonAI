"""
Standalone gateway example (praisonai-bot first).

Install:
    pip install praisonaiagents "praisonai-bot[gateway]"

Set credentials:
    export OPENAI_API_KEY=your_key

Run:
    python bot_standalone_example.py

For Telegram/Discord/Slack channels, use the CLI after onboarding:
    praisonai-bot onboard
    praisonai-bot bot start --platform telegram
"""

import asyncio

from praisonaiagents import Agent
from praisonaiagents.gateway import GatewayConfig
from praisonai_bot.gateway import WebSocketGateway

assistant = Agent(name="assistant", instructions="You are a helpful assistant.")

config = GatewayConfig(host="127.0.0.1", port=8765)
gateway = WebSocketGateway(config=config)
gateway.register_agent(assistant, agent_id="assistant")

if __name__ == "__main__":
    print("Gateway: ws://127.0.0.1:8765  health: http://127.0.0.1:8765/health")
    print("CLI equivalent: praisonai-bot gateway start --host 127.0.0.1 --port 8765")
    asyncio.run(gateway.start())
