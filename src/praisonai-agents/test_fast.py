import time
from praisonaiagents import Agent

t0 = time.time()
agents = [Agent(name=f'Test_{i}', llm='gpt-4o-mini', output='silent') for i in range(100)]
t1 = time.time()

print(f"Time for 100 agents: {t1 - t0:.4f} seconds")
