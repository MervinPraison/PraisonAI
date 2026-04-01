"""Weather Search - Editor Output Example.

Searches for weather, creates JSON data, writes a parser script, executes
it, and lists created files.
"""
from praisonaiagents import Agent
from praisonaiagents.tools import (
    write_file, execute_command, list_files
)

try:
    from praisonaiagents.tools import web_search
    tools = [web_search, write_file, execute_command, list_files]
except ImportError:
    tools = [write_file, execute_command, list_files]

agent = Agent(
    instructions="You are a helpful research assistant.",
    output="editor",
    tools=tools,
    approval=False,
)
agent.start(
    "Search the web for the current weather in Tokyo, create a JSON file at "
    "/tmp/weather_data.json with the findings, then write a Python script at "
    "/tmp/parse_weather.py that reads the JSON and prints a formatted weather "
    "report, execute the script, and list all files you created in /tmp"
)
