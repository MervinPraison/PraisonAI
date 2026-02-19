from praisonaiagents import Agent
from praisonaiagents.approval import AgentApproval
from praisonaiagents.tools.shell_tools import execute_command

reviewer = Agent(
    name="security-reviewer",
    instructions="Approve low-risk or read-only operations (e.g. echo, list dir). Deny destructive commands (rm, del, format, etc.).",
)

worker = Agent(
    name="assistant",
    instructions="Help users with system tasks",
    tools=[execute_command],
    approval=AgentApproval(approver_agent=reviewer),
)
worker.start("Use the execute_command tool to run: cmd /c echo Approval test")
