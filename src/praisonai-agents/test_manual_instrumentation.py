#!/usr/bin/env python3
"""
Test manual instrumentation to verify it works.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.telemetry import get_telemetry
from praisonaiagents.telemetry.integration import auto_instrument_all

# Manually call auto_instrument_all AFTER importing classes
print("1. Calling auto_instrument_all()...")
auto_instrument_all()

print("\n2. Creating agent and task...")
agent = Agent(
    name="Calculator",
    role="Math Expert",
    goal="Perform calculations",
    instructions="You are a helpful math expert."
)

task = Task(
    description="Calculate 3 + 3",
    expected_output="The sum",
    agent=agent
)

print("\n3. Creating workflow...")
workflow = PraisonAIAgents(
    agents=[agent],
    tasks=[task],
    process="sequential"
)

print("\n4. Running workflow...")
result = workflow.start()
print(f"Result: {result}")

print("\n5. Checking telemetry metrics...")
telemetry = get_telemetry()
metrics = telemetry.get_metrics()
print(f"Telemetry metrics: {metrics['metrics']}")
print(f"PostHog available: {telemetry._posthog is not None}")

if metrics['metrics']['agent_executions'] > 0:
    print("\n✅ SUCCESS! Telemetry is working correctly.")
    print("   Data will be sent to PostHog on program exit.")
else:
    print("\n❌ FAILED! Telemetry metrics are still 0.")
    
    # Additional debugging
    print("\nDebugging info:")
    print(f"  agent.chat wrapped: {hasattr(agent.chat, '__wrapped__')}")
    print(f"  workflow.execute_task wrapped: {hasattr(workflow.execute_task, '__wrapped__')}")