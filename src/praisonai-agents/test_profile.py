from line_profiler import profile
from praisonaiagents.agent.agent import Agent

Agent.__init__ = profile(Agent.__init__)

def run_init():
    for _ in range(100):
        # We also need to mock or ensure no external calls actually hit APIs
        Agent(name='Test', llm='gpt-4o-mini', output='silent')

run_init()
