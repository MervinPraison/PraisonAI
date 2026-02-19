"""
Discord Approval Example
========================
Routes tool approvals to a Discord channel.

Requires:
    pip install praisonaiagents praisonai[bot]
    export DISCORD_BOT_TOKEN=MTIz...
    export DISCORD_CHANNEL_ID=1234567890
    export OPENAI_API_KEY=sk-...
"""

from praisonaiagents import Agent
from praisonaiagents.tools.shell_tools import execute_command
from praisonai.bots import DiscordApproval

agent = Agent(
    name="DevOps",
    instructions="You are a DevOps assistant. Use shell tools when asked.",
    tools=[execute_command],
    approval=DiscordApproval(),
)

agent.start("List files in the current directory")
