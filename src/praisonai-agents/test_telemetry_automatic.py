#!/usr/bin/env python3
"""
Test that telemetry works automatically without manual instrumentation.
"""

# NO manual telemetry setup - it should work automatically!
from praisonaiagents import Agent, Task, PraisonAIAgents

# Create a simple agent
agent = Agent(
    name="AutoTelemetryTest",
    role="Math Expert",
    goal="Perform calculations",
    instructions="You are a helpful math expert."
)

# Create a task
task = Task(
    description="Calculate 5 + 5",
    expected_output="The sum",
    agent=agent
)

# Create and run workflow
workflow = PraisonAIAgents(
    agents=[agent],
    tasks=[task],
    process="sequential"
)

print("Running workflow (telemetry should be automatic)...")
result = workflow.start()
print(f"Result: {result}")

# Check if telemetry was collected
from praisonaiagents.telemetry import get_telemetry
telemetry = get_telemetry()

if telemetry.enabled:
    metrics = telemetry.get_metrics()
    print(f"\n✅ Telemetry is working automatically!")
    print(f"- Agent executions: {metrics['metrics']['agent_executions']}")
    print(f"- Task completions: {metrics['metrics']['task_completions']}")
    print(f"- Session ID: {metrics['session_id']}")
    print("\nTelemetry data will be sent to PostHog on program exit.")
else:
    print("\n❌ Telemetry is disabled")