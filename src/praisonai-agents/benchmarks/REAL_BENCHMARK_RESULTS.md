# PraisonAI Agents - Real-World Execution Benchmark

**Generated:** 2025-12-18 14:33:49
**Model:** gpt-4o-mini
**Iterations:** 3 per test

## Results Summary

| Test | PraisonAI (avg) | Agno (avg) | Difference |
|------|-----------------|------------|------------|
| Single Agent | 2.04s | 3.18s | PraisonAI 1.56x faster |
| 2 Agents | 2.49s | 20.49s | PraisonAI 8.21x faster |
| 3 Agents | 6.52s | 13.97s | PraisonAI 2.14x faster |

## Detailed Results

### praisonai_single
- Average: 2.04s
- Min: 1.95s
- Max: 2.19s
- Std Dev: 0.13s
- Times: ['2.19s', '1.95s', '2.00s']

### agno_single
- Average: 3.18s
- Min: 3.00s
- Max: 3.51s
- Std Dev: 0.28s
- Times: ['3.51s', '3.00s', '3.04s']

### praisonai_two_agents
- Average: 2.49s
- Min: 2.22s
- Max: 2.65s
- Std Dev: 0.24s
- Times: ['2.65s', '2.22s', '2.62s']

### agno_two_agents
- Average: 20.49s
- Min: 9.96s
- Max: 35.05s
- Std Dev: 13.02s
- Times: ['16.46s', '9.96s', '35.05s']

### praisonai_three_agents
- Average: 6.52s
- Min: 5.62s
- Max: 7.39s
- Std Dev: 0.88s
- Times: ['5.62s', '6.54s', '7.39s']

### agno_three_agents
- Average: 13.97s
- Min: 11.69s
- Max: 15.32s
- Std Dev: 1.99s
- Times: ['14.91s', '11.69s', '15.32s']

## Package Versions

| Package | Version |
|---------|--------|
| PraisonAI | 0.1.5 |
| Agno | 2.3.14 |

## How to Reproduce

```bash
export OPENAI_API_KEY=your_key
cd praisonai-agents
python benchmarks/real_benchmark.py
```
