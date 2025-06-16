#!/usr/bin/env python3
"""
Debug telemetry instrumentation to see what's happening.
"""

import os
# Make sure telemetry is enabled
if 'PRAISONAI_TELEMETRY_DISABLED' in os.environ:
    del os.environ['PRAISONAI_TELEMETRY_DISABLED']

print("1. Importing modules...")
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.telemetry import get_telemetry

print("\n2. Checking telemetry status...")
telemetry = get_telemetry()
print(f"Telemetry enabled: {telemetry.enabled}")
print(f"PostHog available: {telemetry._posthog is not None}")

print("\n3. Creating agent...")
agent = Agent(
    name="TestAgent",
    role="Test Role",
    goal="Test Goal",
    instructions="Test instructions"
)

# Check if agent.execute is instrumented
print(f"\n4. Checking agent instrumentation...")
print(f"Agent has execute method: {hasattr(agent, 'execute')}")
if hasattr(agent, 'execute'):
    print(f"Execute method type: {type(agent.execute)}")
    print(f"Execute method name: {agent.execute.__name__ if hasattr(agent.execute, '__name__') else 'No name'}")
    print(f"Is wrapped: {'instrumented' in str(agent.execute.__name__) if hasattr(agent.execute, '__name__') else 'Unknown'}")

print("\n5. Creating task...")
task = Task(
    description="Test task",
    expected_output="Test output",
    agent=agent
)

print("\n6. Creating workflow...")
workflow = PraisonAIAgents(
    agents=[agent],
    tasks=[task],
    process="sequential"
)

# Check if workflow.start is instrumented
print(f"\n7. Checking workflow instrumentation...")
print(f"Workflow has start method: {hasattr(workflow, 'start')}")
if hasattr(workflow, 'start'):
    print(f"Start method type: {type(workflow.start)}")
    print(f"Start method name: {workflow.start.__name__ if hasattr(workflow.start, '__name__') else 'No name'}")
    print(f"Is wrapped: {'instrumented' in str(workflow.start.__name__) if hasattr(workflow.start, '__name__') else 'Unknown'}")

print("\n8. Running workflow...")
result = workflow.start()

print("\n9. Checking metrics...")
metrics = telemetry.get_metrics()
print(f"Metrics: {metrics}")

print("\n10. Manually tracking to verify telemetry works...")
telemetry.track_agent_execution("ManualTest", success=True)
telemetry.track_task_completion("ManualTask", success=True)
manual_metrics = telemetry.get_metrics()
print(f"After manual tracking: {manual_metrics['metrics']}")