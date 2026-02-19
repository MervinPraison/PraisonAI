"""
Telegram Approval Example
=========================
Routes tool approvals to a Telegram chat.

Requires:
    pip install praisonaiagents praisonai[bot]
    export TELEGRAM_BOT_TOKEN=123456:ABC-...
    export TELEGRAM_CHAT_ID=987654321
    export OPENAI_API_KEY=sk-...
"""

from praisonaiagents import Agent
from praisonaiagents.tools.shell_tools import execute_command
from praisonai.bots import TelegramApproval

agent = Agent(
    name="DevOps",
    instructions="You are a DevOps assistant. Use shell tools when asked.",
    tools=[execute_command],
    approval=TelegramApproval(),
)

agent.start("List files in the current directory")
