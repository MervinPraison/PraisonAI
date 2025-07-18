from praisonaiagents import Agent
from praisonaiagents.telemetry import force_shutdown_telemetry

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini"
)
agent.start("Why sky is Blue?")

# Ensure telemetry shuts down cleanly
force_shutdown_telemetry()