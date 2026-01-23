# PraisonAI Agents - Tools Benchmark Results

**Generated:** 2026-01-23 11:50:18
**Iterations:** 100
**Test:** Agent instantiation WITH TOOLS

## Results

| Framework | Avg Time (μs) | Relative |
|-----------|---------------|----------|
| **PraisonAI** | **5.30** | **1.00x (fastest)** |
| Agno | 5.62 | 1.06x |
| PraisonAI (LiteLLM) | 11.08 | 2.09x |
| OpenAI Agents SDK | 315.49 | 59.55x |
| LangGraph | 2,511.95 | 474x |
| CrewAI | 41,349.24 | 7,804x |

## Package Versions

| Package | Version |
|---------|--------|
| PraisonAI | 0.13.11 |
| Agno | 2.4.2 |
| OpenAI Agents SDK | 0.6.3 |
| LangGraph | 1.0.7 |
| CrewAI | 1.8.1 |

## How to Reproduce

```bash
cd praisonai-agents
python benchmarks/tools_benchmark.py
```
