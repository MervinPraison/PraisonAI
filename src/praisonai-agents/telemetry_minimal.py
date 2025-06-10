#!/usr/bin/env python3
"""
Minimal example showing telemetry integration with agents.
"""

import os
# Uncomment to disable telemetry
# os.environ['PRAISONAI_TELEMETRY_DISABLED'] = 'true'

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.telemetry import get_telemetry

# Create a simple agent
agent = Agent(
    name="Calculator",
    role="Math Expert",
    goal="Perform calculations",
    instructions="You are a helpful math expert."
)

# Create a task
task = Task(
    description="Calculate 2 + 2",
    expected_output="The sum",
    agent=agent
)

# Create and run workflow
workflow = PraisonAIAgents(
    agents=[agent],
    tasks=[task],
    process="sequential"
)

print("Running workflow with telemetry...")
result = workflow.start()
print(f"Result: {result}")

# Check telemetry metrics
telemetry = get_telemetry()
if telemetry.enabled:
    metrics = telemetry.get_metrics()
    print(f"\nTelemetry metrics collected:")
    print(f"- Agent executions: {metrics['metrics']['agent_executions']}")
    print(f"- Task completions: {metrics['metrics']['task_completions']}")
    print(f"- Errors: {metrics['metrics']['errors']}")
    print(f"- Session ID: {metrics['session_id']}")
else:
    print("\nTelemetry is disabled")

print("\nTo disable telemetry, set any of these environment variables:")
print("- PRAISONAI_TELEMETRY_DISABLED=true")
print("- DO_NOT_TRACK=true")