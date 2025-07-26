#!/usr/bin/env python3

from praisonaiagents import PraisonAIAgents

print("Available methods in PraisonAIAgents:")
methods = [method for method in dir(PraisonAIAgents) if not method.startswith('_')]
for method in sorted(methods):
    print(f"  {method}")

print(f"\nhasattr(PraisonAIAgents, 'run'): {hasattr(PraisonAIAgents, 'run')}")

# Check if start is an alias for run
if hasattr(PraisonAIAgents, 'start'):
    print(f"PraisonAIAgents.start: {PraisonAIAgents.start}")
    print(f"Is start the same as run? {hasattr(PraisonAIAgents, 'run') and PraisonAIAgents.start == getattr(PraisonAIAgents, 'run', None)}")