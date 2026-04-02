import cProfile
import pstats
import io
from praisonaiagents import Agent

# Warm up
for _ in range(100):
    _ = Agent(name="Test", llm="gpt-4o-mini", output="silent")

pr = cProfile.Profile()
pr.enable()

for _ in range(5000):
    _ = Agent(name="Test", llm="gpt-4o-mini", output="silent")

pr.disable()
s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats('cumtime')
ps.print_stats(30)
print(s.getvalue())
