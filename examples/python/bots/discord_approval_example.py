"""Discord Approval — route tool approvals to a Discord channel."""

from praisonaiagents import Agent
from praisonai.bots import DiscordApproval

agent = Agent(
    name="assistant",
    instructions="Help users with system tasks",
    tools=["execute_command"],
    approval=DiscordApproval(channel_id="YOUR_CHANNEL_ID"),  # token from DISCORD_BOT_TOKEN env
)

agent.start("List the files in the current directory")
