"""HTTP Approval — serve a local web dashboard for tool approvals."""

from praisonaiagents import Agent
from praisonai.bots import HTTPApproval

agent = Agent(
    name="assistant",
    instructions="Help users with system tasks",
    tools=["execute_command"],
    approval=HTTPApproval(host="127.0.0.1", port=8899),
)

# When a tool needs approval, open http://127.0.0.1:8899/approve/<request_id>
# in your browser and click Approve or Deny.
agent.start("List the files in the current directory")
