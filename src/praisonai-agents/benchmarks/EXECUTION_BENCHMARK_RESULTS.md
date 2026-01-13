# PraisonAI Agents - Real Execution Benchmark

**Generated:** 2026-01-13 06:07:28
**Model:** gpt-4o-mini
**Iterations:** 3
**Prompt:** "What is 2+2? Reply with just the number."

## Results

| Framework | Method | Avg Time | Relative |
|-----------|--------|----------|----------|
| **PraisonAI (LiteLLM)** | `agent.start()` | **0.55s** | **1.00x (fastest)** |
| PraisonAI | `agent.start()` | 0.64s | 1.15x |
| CrewAI | `crew.kickoff()` | 0.95s | 1.71x |
| Agno | `agent.run()` | 1.05s | 1.90x |

## Package Versions

| Package | Version |
|---------|--------|
| PraisonAI | 0.11.7 |
| Agno | 2.3.25 |
| CrewAI | 1.8.0 |

## How to Reproduce

```bash
export OPENAI_API_KEY=your_key
cd praisonai-agents
python benchmarks/execution_benchmark.py
```
