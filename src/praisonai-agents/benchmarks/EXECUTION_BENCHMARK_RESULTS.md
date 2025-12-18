# PraisonAI Agents - Real Execution Benchmark

**Generated:** 2025-12-18 14:43:52
**Model:** gpt-4o-mini
**Iterations:** 3
**Prompt:** "What is 2+2? Reply with just the number."

## Results

| Framework | Method | Avg Time | Relative |
|-----------|--------|----------|----------|
| **PraisonAI** | `agent.start()` | **0.45s** | **1.00x (fastest)** |
| PraisonAI (LiteLLM) | `agent.start()` | 0.55s | 1.22x |
| CrewAI | `crew.kickoff()` | 0.58s | 1.28x |
| Agno | `agent.run()` | 0.92s | 2.05x |

## Package Versions

| Package | Version |
|---------|--------|
| PraisonAI | 0.1.5 |
| Agno | 2.3.14 |
| CrewAI | 1.6.1 |

## How to Reproduce

```bash
export OPENAI_API_KEY=your_key
cd praisonai-agents
python benchmarks/execution_benchmark.py
```
