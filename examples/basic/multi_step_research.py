"""Multi-Step Research - Editor Output Example.

Researches Python frameworks, creates comparison code, runs it, writes a
markdown report, reads it back, lists files, and gets system info.
"""
from praisonaiagents import Agent
from praisonaiagents.tools import (
    write_file, read_file, execute_command, list_directory, get_system_info
)

try:
    from praisonaiagents.tools import web_search
    tools = [web_search, write_file, read_file, execute_command,
             list_directory, get_system_info]
except ImportError:
    tools = [write_file, read_file, execute_command,
             list_directory, get_system_info]

agent = Agent(
    instructions="You are a helpful research assistant.",
    output="editor",
    tools=tools,
    approval=True,
)
agent.start(
    "Research the top 3 Python web frameworks (Django, FastAPI, Flask), then: "
    "1) Search the web for each framework's latest version and key features, "
    "2) Create a file called /tmp/framework_comparison.py that contains a "
    "Python dictionary with the comparison data, "
    "3) Execute the code to verify the dictionary is valid, "
    "4) Write a markdown report to /tmp/framework_report.md summarizing your "
    "findings in a table format, "
    "5) Read back the report file to verify it was written correctly, "
    "6) List the files in /tmp to confirm both files exist, "
    "7) Get system info to note what OS this report was generated on"
)
