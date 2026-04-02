import time
from praisonaiagents import Agent as PraisonAgent

def measure_instantiation(create_fn, iterations=1000, warmup=50):
    for _ in range(warmup):
        create_fn()
    
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        create_fn()
        times.append((time.perf_counter() - start) * 1_000_000)
    return sum(times) / len(times)

r1 = measure_instantiation(lambda: PraisonAgent(name='Test', llm='gpt-4o-mini', output="silent"))
r2 = measure_instantiation(lambda: PraisonAgent(name='Test', llm='openai/gpt-4o-mini', output="silent"))
print(f"PraisonAI: {r1:.2f} μs")
print(f"PraisonAI (LiteLLM): {r2:.2f} μs")
