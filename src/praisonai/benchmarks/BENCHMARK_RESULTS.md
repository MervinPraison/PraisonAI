# PraisonAI CLI - Benchmark Results

**Generated:** 2025-12-19 16:04:40

## Import Times

| Module | Time (ms) | Target | Status |
|--------|-----------|--------|--------|
| praisonai | 4.11 | <10 | ✅ |
| message_queue | 6.87 | <50 | ✅ |
| at_mentions | 0.58 | <50 | ✅ |
| profiler | 0.90 | <10 | ✅ |

## Instantiation Times

| Class | Time (μs) | Target | Status |
|-------|-----------|--------|--------|
| MessageQueue | 0.26 | <100 | ✅ |
| StateManager | 0.30 | <100 | ✅ |
| FileSearchService | 8.42 | <100 | ✅ |

## Lazy Loading

| Operation | Time (ms) |
|-----------|----------|
| PraisonAI lazy load | 3886.47 |

## How to Reproduce

```bash
cd praisonai
python benchmarks/simple_benchmark.py
```
