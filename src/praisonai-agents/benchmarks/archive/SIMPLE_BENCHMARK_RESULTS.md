> **Superseded.** Historical result from 2025-12-18, kept for reference only. Package versions and methodology differ from current runs; do not cite. Current results: [../BENCHMARK_RESULTS.md](../BENCHMARK_RESULTS.md).

# PraisonAI Agents - Benchmark Results

**Generated:** 2025-12-18 13:23:43

## Agent Instantiation Time

| Framework | Avg Time (μs) | Relative |
|-----------|---------------|----------|
| **PraisonAI** | **4.16** | **1.00x (fastest)** |
| OpenAI Agents SDK | 5.55 | 1.33x |
| Agno | 5.58 | 1.34x |
| PraisonAI (LiteLLM) | 8.52 | 2.05x |
| PydanticAI | 225.87 | 54.25x |
| LangGraph | 4,349.54 | 1,045x |
| CrewAI | 15,911.11 | 3,821x |

## How to Reproduce

```bash
cd praisonai-agents
python benchmarks/simple_benchmark.py
```
