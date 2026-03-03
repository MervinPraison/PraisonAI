"""Calculator with Tests - Editor Output Example.

Builds a calculator module, writes unit tests, runs them, generates a
coverage-style report, and reads it back.
"""
from praisonaiagents import Agent
from praisonaiagents.tools import (
    write_file, read_file, execute_command
)

agent = Agent(
    instructions="You are a helpful coding assistant.",
    output="editor",
    tools=[write_file, read_file, execute_command],
    approval=True,
)
agent.start(
    "Build a mini calculator - create /tmp/calculator.py with add, subtract, "
    "multiply, divide functions, write unit tests in /tmp/test_calculator.py "
    "using unittest, run the tests to make sure they pass, then generate a "
    "coverage-style report in /tmp/calc_report.md listing which functions were "
    "tested and read it back"
)
