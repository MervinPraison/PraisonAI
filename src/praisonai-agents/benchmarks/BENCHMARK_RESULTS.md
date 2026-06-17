# PraisonAI Agents - Benchmark Results

**Generated:** 2026-06-17
**Methodology:** 10 warmup runs + 1000 measured iterations (`performance_benchmark.py` config)
**Config:** `Agent(name=..., instructions=..., model="gpt-4o-mini", tools=[get_weather], output="silent")`

## Agent Instantiation Time

| Framework | Avg Time (μs) | Min (μs) | Median (μs) | Relative |
|-----------|---------------|----------|-------------|----------|
| OpenAI Agents SDK | 5.05 | — | — | 1.00x (fastest) |
| Agno | 5.27 | — | — | 1.04x |
| **PraisonAI** | **13.62** | **12.58** | **12.96** | **2.69x** |
| PraisonAI (LiteLLM) | 14.49 | 13.37 | 13.71 | 2.86x |

### PraisonAI detail (1000 iter)

| Variant | Avg (μs) | Min (μs) | Median (μs) | Std (μs) |
|---------|----------|----------|-------------|----------|
| With tools (`gpt-4o-mini`) | 13.62 | 12.58 | 12.96 | 2.73 |
| With tools (`openai/gpt-4o-mini`) | 14.49 | 13.37 | 13.71 | 4.14 |
| Minimal, no tools | 13.40 | — | — | — |

## Historical baseline

| Source | Config | Avg (μs) | Notes |
|--------|--------|----------|-------|
| `performance_benchmark.py` (Dec 2025) | tools + 1000 iter | **3.20** | Pre-init-bloat baseline |
| `simple_benchmark.py` (Dec 2025) | no tools, 100 iter | **3.77** | Saved in prior `BENCHMARK_RESULTS.md` |
| Current (Jun 2026) | tools + 1000 iter | **13.62** | After lazy-init optimisations (was ~31 μs pre-fix) |

## Package Versions

| Package | Version |
|---------|---------|
| PraisonAI | 1.6.60 |
| Agno | 2.4.2 |
| OpenAI Agents SDK | 0.7.0 |

## How to Reproduce

PraisonAI-only (fast; avoids CrewAI/LangGraph import hang):

```bash
cd praisonai-agents
PYTHONWARNINGS='ignore::DeprecationWarning' python -c "
import time, statistics
from typing import Literal
from praisonaiagents import Agent

def get_weather(city: Literal['nyc', 'sf']):
    return 'cloudy' if city == 'nyc' else 'sunny'

def bench(fn, n=1000, w=10):
    for _ in range(w): fn()
    times = []
    for _ in range(n):
        s = time.perf_counter(); fn(); times.append(time.perf_counter()-s)
    print(f'avg={statistics.mean(times)*1e6:.2f} μs')

bench(lambda: Agent(name='Test', instructions='Hi', model='gpt-4o-mini', tools=[get_weather], output='silent'))
"
```

Full multi-framework benchmark:

```bash
cd praisonai-agents
PYTHONWARNINGS='ignore::DeprecationWarning' python benchmarks/performance_benchmark.py --save
```
