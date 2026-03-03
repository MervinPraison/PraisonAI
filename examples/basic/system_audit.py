"""System Audit - Editor Output Example.

Runs system commands, gathers info, writes a report, and reads it back.
"""
from praisonaiagents import Agent
from praisonaiagents.tools import (
    write_file, read_file, execute_command
)

agent = Agent(
    instructions="You are a helpful system administration assistant.",
    output="editor",
    tools=[write_file, read_file, execute_command],
    approval=True,
)
agent.start(
    "Investigate my system - get the current date, check disk usage, find out "
    "what Python version is installed, list running processes sorted by memory, "
    "then write all findings to /tmp/system_audit.md as a neat report and read "
    "it back to verify"
)
