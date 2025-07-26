#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

try:
    from praisonaiagents.agents.agents import PraisonAIAgents
    print("Methods containing 'run':", [m for m in dir(PraisonAIAgents) if 'run' in m.lower()])
    print("Has run method:", hasattr(PraisonAIAgents, 'run'))
    
    if hasattr(PraisonAIAgents, 'run'):
        print("run method is:", PraisonAIAgents.run)
        if hasattr(PraisonAIAgents, 'start'):
            print("run == start?", PraisonAIAgents.run == PraisonAIAgents.start)
            print("run is start?", PraisonAIAgents.run is PraisonAIAgents.start)
    
    print("\nAll methods:")
    for method in sorted(dir(PraisonAIAgents)):
        if not method.startswith('_'):
            print(f"  {method}")
            
except Exception as e:
    import traceback
    print("Error:", e)
    print("Traceback:")
    traceback.print_exc()