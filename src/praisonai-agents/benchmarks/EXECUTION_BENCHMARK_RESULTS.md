# PraisonAI Agents - Real Execution Benchmark

**Generated:** 2026-01-13 05:32:09
**Model:** gpt-4o-mini
**Iterations:** 3
**Prompt:** "What is 2+2? Reply with just the number."

## Results

| Framework | Method | Avg Time | Relative |
|-----------|--------|----------|----------|
| **PraisonAI** | `agent.start()` | **0.61s** | **1.00x (fastest)** |
| PraisonAI (LiteLLM) | `agent.start()` | 0.69s | 1.13x |
| CrewAI | `crew.kickoff()` | 0.85s | 1.39x |
| Agno | `agent.run()` | 1.06s | 1.72x |

## Package Versions

| Package | Version |
|---------|--------|
| PraisonAI | 0.11.7 |
| Agno | 2.3.14 |
| CrewAI | 1.6.1 |

## How to Reproduce

```bash
export OPENAI_API_KEY=your_key
cd praisonai-agents
python benchmarks/execution_benchmark.py
```
