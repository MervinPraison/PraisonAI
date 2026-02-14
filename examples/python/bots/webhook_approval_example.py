"""Webhook Approval — route tool approvals to an external HTTP endpoint."""

from praisonaiagents import Agent
from praisonai.bots import WebhookApproval

agent = Agent(
    name="assistant",
    instructions="Help users with system tasks",
    tools=["execute_command"],
    approval=WebhookApproval(
        webhook_url="https://your-app.com/api/approvals",
        headers={"Authorization": "Bearer YOUR_TOKEN"},
    ),
)

agent.start("List the files in the current directory")
