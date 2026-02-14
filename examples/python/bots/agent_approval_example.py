"""Agent Approval — delegate tool approvals to another AI agent."""

from praisonaiagents import Agent
from praisonaiagents.approval import AgentApproval

# Create a security reviewer agent
reviewer = Agent(
    name="security-reviewer",
    instructions=(
        "You are a security reviewer. Only approve low-risk read operations. "
        "Deny anything destructive like delete, remove, or write operations. "
        "Respond with exactly one word: APPROVE or DENY"
    ),
)

# Create a worker agent that uses the reviewer for approvals
worker = Agent(
    name="assistant",
    instructions="Help users with system tasks",
    tools=["execute_command"],
    approval=AgentApproval(approver_agent=reviewer),
)

worker.start("List the files in the current directory")
