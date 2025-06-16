#!/usr/bin/env python3
"""
Debug double-counting in telemetry.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.telemetry import get_telemetry

# Get telemetry instance
telemetry = get_telemetry()

# Clear any existing metrics by flushing
telemetry.flush()

print("Starting fresh telemetry tracking...\n")

# Create ONE agent
print("Creating 1 agent...")
agent = Agent(
    name="SingleAgent",
    role="Test Role",
    goal="Test Goal",
    instructions="Test instructions"
)

# Create ONE task
print("Creating 1 task...")
task = Task(
    description="Single test task",
    expected_output="Test output",
    agent=agent
)

# Create workflow with ONE agent and ONE task
print("Creating workflow with 1 agent and 1 task...")
workflow = PraisonAIAgents(
    agents=[agent],
    tasks=[task],
    process="sequential"
)

# Check metrics before running
metrics_before = telemetry.get_metrics()
print(f"\nMetrics BEFORE running workflow:")
print(f"  Agent executions: {metrics_before['metrics']['agent_executions']}")
print(f"  Task completions: {metrics_before['metrics']['task_completions']}")

# Run the workflow
print("\nRunning workflow...")
result = workflow.start()

# Check metrics after running
metrics_after = telemetry.get_metrics()
print(f"\nMetrics AFTER running workflow:")
print(f"  Agent executions: {metrics_after['metrics']['agent_executions']} (expected: 1)")
print(f"  Task completions: {metrics_after['metrics']['task_completions']} (expected: 1)")

if metrics_after['metrics']['agent_executions'] > 1:
    print("\n❌ ISSUE: Agent executions are being double-counted!")
    print("   Possible causes:")
    print("   - Agent method is being called multiple times")
    print("   - Instrumentation is being applied twice")
    print("   - Multiple tracking calls for same execution")

if metrics_after['metrics']['task_completions'] > 1:
    print("\n❌ ISSUE: Task completions are being double-counted!")
    print("   Possible causes:")
    print("   - Task completion is tracked in multiple places")
    print("   - Instrumentation is being applied twice")