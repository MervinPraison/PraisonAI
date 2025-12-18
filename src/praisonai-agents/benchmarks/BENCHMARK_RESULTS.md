# PraisonAI Agents - Benchmark Results

**Generated:** 2025-12-18 14:40:22
**Iterations:** 100
**Test:** Agent instantiation (without tools)

## Results

| Framework | Avg Time (μs) | Relative |
|-----------|---------------|----------|
| **PraisonAI** | **3.77** | **1.00x (fastest)** |
| OpenAI Agents SDK | 5.26 | 1.39x |
| Agno | 5.64 | 1.49x |
| PraisonAI (LiteLLM) | 7.56 | 2.00x |
| PydanticAI | 226.94 | 60.16x |
| LangGraph | 4,558.71 | 1,209x |
| CrewAI | 15,607.92 | 4,138x |

## Package Versions

| Package | Version |
|---------|--------|
| PraisonAI | 0.1.5 |
| Agno | 2.3.14 |
| PydanticAI | 1.35.0 |
| OpenAI Agents SDK | 0.6.3 |
| LangGraph | 1.0.5 |
| CrewAI | 1.6.1 |

## How to Reproduce

```bash
cd praisonai-agents
python benchmarks/simple_benchmark.py
```
