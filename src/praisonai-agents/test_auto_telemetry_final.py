#!/usr/bin/env python3
"""
Final test of automatic telemetry.
"""

print("Step 1: Import praisonaiagents...")
from praisonaiagents import Agent, Task, PraisonAIAgents, get_telemetry

print("\nStep 2: Check if telemetry is initialized...")
telemetry = get_telemetry()
print(f"  Telemetry enabled: {telemetry.enabled}")
print(f"  PostHog available: {telemetry._posthog is not None}")

print("\nStep 3: Check if Agent class is instrumented...")
print(f"  Agent.__init__.__name__: {Agent.__init__.__name__}")

print("\nStep 4: Create an agent...")
agent = Agent(name="Test", role="Test", goal="Test", instructions="Test")
print(f"  agent.chat wrapped: {hasattr(agent.chat, '__wrapped__')}")

print("\nStep 5: Create and run a simple workflow...")
task = Task(description="Say hello", expected_output="A greeting", agent=agent)
workflow = PraisonAIAgents(agents=[agent], tasks=[task], process="sequential")

# Check workflow instrumentation
print(f"  workflow.execute_task wrapped: {hasattr(workflow.execute_task, '__wrapped__')}")

result = workflow.start()
print(f"\nResult: {result}")

print("\nStep 6: Check metrics...")
metrics = telemetry.get_metrics()
print(f"  Metrics: {metrics['metrics']}")

if metrics['metrics']['agent_executions'] > 0:
    print("\n✅ Automatic telemetry is working!")
else:
    print("\n❌ Automatic telemetry is NOT working")
    print("\nPossible reason: The auto_instrument_all() in __init__.py might be")
    print("running before the telemetry module's lazy initialization completes.")