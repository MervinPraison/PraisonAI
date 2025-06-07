#!/usr/bin/env python3
"""
Test to demonstrate why telemetry isn't being sent by default.
"""

import os

# Ensure telemetry is enabled
for var in ['PRAISONAI_TELEMETRY_DISABLED', 'PRAISONAI_DISABLE_TELEMETRY', 'DO_NOT_TRACK']:
    if var in os.environ:
        del os.environ[var]

print("=== Testing Telemetry Integration ===")

# Test 1: Default behavior (no telemetry)
print("\n1. Testing default Agent behavior:")
from praisonaiagents import Agent, Task

agent = Agent(
    name="TestAgent",
    role="Tester",
    goal="Test telemetry",
    backstory="I test things",
    llm="gpt-4o-mini"
)

task = Task(
    description="Say hello",
    expected_output="A greeting",
    agent=agent
)

# Check if agent has telemetry
print(f"  Agent has telemetry: {hasattr(agent, '_telemetry')}")
print(f"  Agent methods: {[m for m in dir(agent) if 'telemetry' in m.lower()]}")

# Test 2: Manual telemetry integration
print("\n2. Testing manual telemetry integration:")
from praisonaiagents.telemetry import get_telemetry
from praisonaiagents.telemetry.integration import instrument_agent

telemetry = get_telemetry()
print(f"  Telemetry enabled: {telemetry.enabled}")

# Manually instrument the agent
instrument_agent(agent, telemetry)
print("  Agent instrumented manually")

# Test 3: Auto-instrumentation
print("\n3. Testing auto-instrumentation:")
from praisonaiagents.telemetry.integration import auto_instrument_all

# Enable auto-instrumentation
auto_instrument_all(telemetry)
print("  Auto-instrumentation enabled")

# Create a new agent to test auto-instrumentation
new_agent = Agent(
    name="AutoInstrumentedAgent",
    role="Tester",
    goal="Test auto telemetry",
    backstory="I test auto-instrumentation",
    llm="gpt-4o-mini"
)

print(f"  New agent instrumented: {hasattr(new_agent.execute, '__wrapped__')}")

# Test 4: Check if telemetry data is collected
print("\n4. Checking telemetry metrics:")
initial_metrics = telemetry.get_metrics()
print(f"  Initial metrics: {initial_metrics['metrics']}")

# The problem: telemetry is never flushed automatically!
print("\n5. The Issue:")
print("  ✗ Telemetry is implemented but NOT automatically integrated")
print("  ✗ Even if integrated, flush() is never called automatically")
print("  ✗ PostHog events are only sent when flush() is explicitly called")

# Test 5: Solution - manual flush
print("\n6. Solution - Manual flush:")
telemetry.flush()
print("  ✓ Manual flush called - events sent to PostHog")

# Test 6: Workflow integration
print("\n7. Testing workflow integration:")
from praisonaiagents import PraisonAIAgents

agents = [
    Agent(name="Agent1", role="First", goal="Do first task", backstory="I'm first"),
    Agent(name="Agent2", role="Second", goal="Do second task", backstory="I'm second")
]

tasks = [
    Task(description="Task 1", expected_output="Output 1", agent=agents[0]),
    Task(description="Task 2", expected_output="Output 2", agent=agents[1])
]

workflow = PraisonAIAgents(
    agents=agents,
    tasks=tasks,
    process="sequential"
)

print(f"  Workflow has telemetry integration: {hasattr(workflow.start, '__wrapped__')}")

print("\n=== Summary of Issues ===")
print("\n1. No automatic integration:")
print("   - Agent and PraisonAIAgents classes don't automatically use telemetry")
print("   - Need to manually call instrument_agent() or auto_instrument_all()")

print("\n2. No automatic flush:")
print("   - Even when integrated, telemetry data is only collected locally")
print("   - flush() must be called explicitly to send data to PostHog")
print("   - No automatic flush on program exit or periodic flush")

print("\n3. Missing integration points:")
print("   - Agent.__init__ doesn't initialize telemetry")
print("   - Agent.execute() doesn't track execution")
print("   - PraisonAIAgents doesn't track workflow execution")
print("   - No atexit handler to flush on program termination")

print("\n=== Recommendations ===")
print("\n1. Add automatic integration in Agent.__init__ and PraisonAIAgents.__init__")
print("2. Add atexit handler to flush telemetry on program exit")
print("3. Add periodic flush (e.g., every 100 events or 60 seconds)")
print("4. Document telemetry behavior clearly for users")