from praisonaiagents import AutoAgents
from praisonaiagents.tools import duckduckgo

agents = AutoAgents(
    instructions="Search for information about AI Agents",
    tools=[duckduckgo],
    process="sequential",
    verbose=True
)

agents.start()