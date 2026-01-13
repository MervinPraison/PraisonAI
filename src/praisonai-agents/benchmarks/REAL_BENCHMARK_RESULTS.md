# PraisonAI Agents - Real-World Execution Benchmark

**Generated:** 2026-01-13 14:42:59
**Model:** gpt-4o-mini
**Iterations:** 3 per test

## Results Summary

| Test | PraisonAI (avg) | Agno (avg) | Difference |
|------|-----------------|------------|------------|
| Single Agent | 2.46s | 2.92s | PraisonAI 1.19x faster |
| 2 Agents | 3.21s | 19.39s | PraisonAI 6.05x faster |
| 3 Agents | 8.26s | 15.01s | PraisonAI 1.82x faster |

## Detailed Results

### praisonai_single
- Average: 2.46s
- Min: 1.93s
- Max: 2.90s
- Std Dev: 0.49s
- Times: ['1.93s', '2.55s', '2.90s']

### agno_single
- Average: 2.92s
- Min: 2.85s
- Max: 2.97s
- Std Dev: 0.06s
- Times: ['2.97s', '2.85s', '2.94s']

### praisonai_two_agents
- Average: 3.21s
- Min: 2.80s
- Max: 3.67s
- Std Dev: 0.44s
- Times: ['3.67s', '2.80s', '3.15s']

### agno_two_agents
- Average: 19.39s
- Min: 10.62s
- Max: 26.06s
- Std Dev: 7.93s
- Times: ['26.06s', '10.62s', '21.50s']

### praisonai_three_agents
- Average: 8.26s
- Min: 6.44s
- Max: 11.88s
- Std Dev: 3.13s
- Times: ['6.47s', '6.44s', '11.88s']

### agno_three_agents
- Average: 15.01s
- Min: 14.46s
- Max: 15.90s
- Std Dev: 0.78s
- Times: ['15.90s', '14.46s', '14.68s']

## Package Versions

| Package | Version |
|---------|--------|
| PraisonAI | 0.11.22 |
| Agno | 2.3.25 |

## How to Reproduce

```bash
export OPENAI_API_KEY=your_key
cd praisonai-agents
python benchmarks/real_benchmark.py
```
