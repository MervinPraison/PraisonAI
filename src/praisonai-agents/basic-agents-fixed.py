#!/usr/bin/env python3

from praisonaiagents import Agent, force_shutdown_telemetry

print("Creating agent...")
agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini"
)

print("Starting agent...")
result = agent.start("Why is the sky blue?")

print("Agent completed successfully!")
print(f"Result: {result}")

# Optional: Clean up telemetry system when script is completely done
print("Cleaning up telemetry...")
force_shutdown_telemetry()

print("Script finished normally.") 