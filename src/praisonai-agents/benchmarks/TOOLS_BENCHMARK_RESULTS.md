# PraisonAI Agents - Tools Benchmark Results

**Generated:** 2025-12-18 14:40:35
**Iterations:** 100
**Test:** Agent instantiation WITH TOOLS

## Results

| Framework | Avg Time (μs) | Relative |
|-----------|---------------|----------|
| **PraisonAI** | **3.24** | **1.00x (fastest)** |
| Agno | 5.12 | 1.58x |
| PraisonAI (LiteLLM) | 8.59 | 2.65x |
| OpenAI Agents SDK | 279.95 | 86.44x |
| LangGraph | 2,310.82 | 713x |
| CrewAI | 15,773.44 | 4,870x |

## Package Versions

| Package | Version |
|---------|--------|
| PraisonAI | 0.1.5 |
| Agno | 2.3.14 |
| OpenAI Agents SDK | 0.6.3 |
| LangGraph | 1.0.5 |
| CrewAI | 1.6.1 |

## How to Reproduce

```bash
cd praisonai-agents
python benchmarks/tools_benchmark.py
```
