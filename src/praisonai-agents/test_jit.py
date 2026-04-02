#!/usr/bin/env python3
"""Quick smoke test for JIT hydration changes."""
import sys
try:
    from praisonaiagents import Agent
    a = Agent(instructions='test')
    print('SUCCESS: Agent created')
    sys.exit(0)
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
