#!/usr/bin/env python3
"""
Debug auto-instrumentation.
"""

print("1. Import telemetry module...")
import praisonaiagents.telemetry
print("   Telemetry module imported")

print("\n2. Check if auto_instrument_all was called...")
print(f"   _initialized: {praisonaiagents.telemetry._initialized}")

print("\n3. Import Agent and PraisonAIAgents...")
from praisonaiagents import Agent, PraisonAIAgents
print("   Classes imported")

print("\n4. Check if classes are instrumented...")
agent = Agent(name="Test", role="Test", goal="Test", instructions="Test")
print(f"   Agent.__init__ name: {Agent.__init__.__name__}")
print(f"   agent.execute exists: {hasattr(agent, 'execute')}")

print("\n5. Manually call auto_instrument_all...")
from praisonaiagents.telemetry.integration import auto_instrument_all
auto_instrument_all()
print("   auto_instrument_all() called")

print("\n6. Create new agent after instrumentation...")
agent2 = Agent(name="Test2", role="Test2", goal="Test2", instructions="Test2")
print(f"   Agent.__init__ name after: {Agent.__init__.__name__}")
print(f"   agent2.execute exists: {hasattr(agent2, 'execute')}")

print("\n7. Check if execute is wrapped...")
if hasattr(agent2, 'execute'):
    print(f"   agent2.execute name: {agent2.execute.__name__}")
    print(f"   agent2.execute wrapped: {hasattr(agent2.execute, '__wrapped__')}")

print("\n8. Import telemetry and check if it's working...")
from praisonaiagents.telemetry import get_telemetry
telemetry = get_telemetry()
print(f"   Telemetry enabled: {telemetry.enabled}")
print(f"   PostHog available: {telemetry._posthog is not None}")

# The key insight: auto_instrument_all needs to be called AFTER
# the Agent and PraisonAIAgents classes are imported!