# PraisonAI Agents - Real-World Execution Benchmark

**Generated:** 2026-01-13 06:05:09
**Model:** gpt-4o-mini
**Iterations:** 3 per test

## Results Summary

| Test | PraisonAI (avg) | Agno (avg) | Difference |
|------|-----------------|------------|------------|
| Single Agent | 2.09s | 3.25s | PraisonAI 1.55x faster |
| 2 Agents | 2.50s | 9.73s | PraisonAI 3.89x faster |
| 3 Agents | 6.25s | 13.56s | PraisonAI 2.17x faster |

## Detailed Results

### praisonai_single
- Average: 2.09s
- Min: 1.64s
- Max: 2.84s
- Std Dev: 0.66s
- Times: ['2.84s', '1.79s', '1.64s']

### agno_single
- Average: 3.25s
- Min: 3.14s
- Max: 3.35s
- Std Dev: 0.10s
- Times: ['3.35s', '3.25s', '3.14s']

### praisonai_two_agents
- Average: 2.50s
- Min: 2.38s
- Max: 2.75s
- Std Dev: 0.21s
- Times: ['2.38s', '2.75s', '2.38s']

### agno_two_agents
- Average: 9.73s
- Min: 9.34s
- Max: 10.53s
- Std Dev: 0.69s
- Times: ['10.53s', '9.34s', '9.34s']

### praisonai_three_agents
- Average: 6.25s
- Min: 5.86s
- Max: 6.80s
- Std Dev: 0.49s
- Times: ['6.80s', '6.09s', '5.86s']

### agno_three_agents
- Average: 13.56s
- Min: 12.26s
- Max: 14.90s
- Std Dev: 1.32s
- Times: ['14.90s', '13.51s', '12.26s']

## Package Versions

| Package | Version |
|---------|--------|
| PraisonAI | 0.11.7 |
| Agno | 2.3.25 |

## How to Reproduce

```bash
export OPENAI_API_KEY=your_key
cd praisonai-agents
python benchmarks/real_benchmark.py
```
