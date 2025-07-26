#!/usr/bin/env python3

# Let me check the very end of the agents.py file to see if there's any assignment after the class
with open('/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents/praisonaiagents/agents/agents.py', 'r') as f:
    lines = f.readlines()

print("Last 10 lines of agents.py:")
for i, line in enumerate(lines[-10:], start=len(lines)-9):
    print(f"{i:4d}: {line.rstrip()}")

print("\nSearching for any 'run =' assignment in the entire file...")
for i, line in enumerate(lines, start=1):
    if 'run =' in line and not line.strip().startswith('#'):
        print(f"Line {i}: {line.strip()}")

print("\nSearching for 'PraisonAIAgents.run' assignment in the entire file...")
for i, line in enumerate(lines, start=1):
    if 'PraisonAIAgents.run' in line:
        print(f"Line {i}: {line.strip()}")