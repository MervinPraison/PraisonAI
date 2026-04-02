import cProfile
import pstats
import io
import time
from praisonaiagents import Agent

def func():
    return Agent(name='Test', llm='gpt-4o-mini', output="silent")

# Warm up to fill caches
for _ in range(100):
    func()

start_time = time.perf_counter()
for _ in range(1000):
    func()
end_time = time.perf_counter()
avg_time = (end_time - start_time) / 1000 * 1_000_000
print(f"Time without profile: {avg_time:.2f} μs")

pr = cProfile.Profile()
pr.enable()

for _ in range(1000):
    func()

pr.disable()
s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats('cumtime')
ps.print_stats(30)
print(s.getvalue())
