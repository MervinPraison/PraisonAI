"""Telegram Approval — route tool approvals to a Telegram chat."""

from praisonaiagents import Agent
from praisonai.bots import TelegramApproval

agent = Agent(
    name="assistant",
    instructions="Help users with system tasks",
    tools=["execute_command"],
    approval=TelegramApproval(chat_id="YOUR_CHAT_ID"),  # token from TELEGRAM_BOT_TOKEN env
)

agent.start("List the files in the current directory")
