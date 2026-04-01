"""Fibonacci Generator - Editor Output Example.

Creates a Fibonacci script, runs it, writes a summary, and reads back
both files to verify everything looks good.
"""
from praisonaiagents import Agent
from praisonaiagents.tools import (
    write_file, read_file, execute_command, list_files
)

agent = Agent(
    instructions="You are a helpful coding assistant.",
    output="editor",
    tools=[write_file, read_file, execute_command, list_files],
    approval=False,
)
agent.start(
    "Create a Python file at /tmp/fibonacci.py that generates the first 20 "
    "Fibonacci numbers, run it to verify the output is correct, then write "
    "a summary to /tmp/fib_summary.md explaining the algorithm you used and "
    "the output, finally read back both files to confirm everything looks good"
)
