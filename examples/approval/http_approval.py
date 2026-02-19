"""
HTTP Approval Example
=====================
Opens a local web dashboard for tool approvals.

Requires:
    pip install praisonaiagents praisonai[bot]
    export OPENAI_API_KEY=sk-...
"""

from praisonaiagents import Agent
from praisonaiagents.tools.shell_tools import execute_command
from praisonai.bots import HTTPApproval

agent = Agent(
    name="DevOps",
    instructions="You are a DevOps assistant. Use shell tools when asked.",
    tools=[execute_command],
    approval=HTTPApproval(),
)

agent.start("List files in the current directory")
