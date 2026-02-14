"""Slack Approval — route tool approvals to a Slack channel."""

from praisonaiagents import Agent
from praisonai.bots import SlackApproval

agent = Agent(
    name="assistant",
    instructions="Help users with system tasks",
    tools=["execute_command"],
    approval=SlackApproval(channel="#approvals"),  # token from SLACK_BOT_TOKEN env
)

agent.start("List the files in the current directory")
