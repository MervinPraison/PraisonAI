#!/usr/bin/env python3
"""
Simple test to check telemetry.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.telemetry import get_telemetry

# Create workflow
agent = Agent(name="Test", role="Tester", goal="Test", instructions="Test")
task = Task(description="Test", expected_output="Test", agent=agent)
workflow = PraisonAIAgents(agents=[agent], tasks=[task], process="sequential")

# Run workflow
print("Running workflow...")
result = workflow.start()

# Check telemetry
telemetry = get_telemetry()
metrics = telemetry.get_metrics()
print(f"\nTelemetry metrics: {metrics['metrics']}")
print(f"Session ID: {metrics['session_id']}")

# Check if telemetry will be sent
print(f"\nTelemetry enabled: {telemetry.enabled}")
print(f"PostHog client available: {telemetry._posthog is not None}")

if telemetry._posthog:
    print("\n✅ Telemetry will be sent to PostHog on program exit")