# Agent Instantiation — Root Cause Analysis

**Date:** 2026-06-17  
**Version:** praisonaiagents 1.6.58 (dev)  
**Methodology:** 10 warmup + 1000 measured iterations, `time.perf_counter()`

## Summary

Instantiation regressed from **~3.2 μs** (Dec 2025) to **~31 μs** (~10×). After fixes, steady-state is **~16 μs** (~2× historical). PraisonAI is competitive with Agno (~5 μs) on warmed benchmarks using `model=`.

## Before vs After Fixes

| Config | Historical | Pre-fix | Post-fix |
|--------|------------|---------|----------|
| Minimal (`name`, `output="silent"`) | 3.20 μs | 31.36 μs | **16.35 μs** |
| `model="gpt-4o-mini"` | 3.77 μs | 32.19 μs | **16.86 μs** |
| `llm="gpt-4o-mini"` (deprecated) | 3.77 μs | 46.48 μs | **~18 μs** (warn once) |
| LiteLLM `openai/gpt-4o-mini` cold | 7.31 μs | **3.7 s** | **53.63 μs** |
| LiteLLM warmed instantiate | — | 60 μs | **19.83 μs** |
| Import `Agent` | — | 20.8 ms | **29.6 ms** |

## Root Causes (validated)

| ID | Cause | Status | Fix applied |
|----|-------|--------|-------------|
| H1 | Config loader cold start (+9 ms first init) | CONFIRMED | Fast path when no config defaults (`_defaults_has_any_values`) |
| H2 | LoopGuard on every init (~2 μs) | CONFIRMED | Lazy `_ensure_loop_guard()` on first tool call |
| H3 | Approval presets | REJECTED | No change needed |
| H4 | `llm=` deprecation every init (+16 μs) | CONFIRMED | Warn once per process in `warn_deprecated_param` |
| H5 | Init bloat / config resolution (~25 μs) | CONFIRMED | Partially addressed via loader fast path |
| H6 | LiteLLM eager `LLM()` import (+3.7 s) | CONFIRMED | Deferred `_llm_init_params` + lazy `llm_instance` property |
| H7 | `ExecutionConfig` deprecation every init | CONFIRMED | Fixed stack walk; internal SDK path cached |

## cProfile — Post-fix (500 warmed `model=` inits)

| Function | Time (ms) | Per call |
|----------|-----------|----------|
| `Agent.__init__` | 8 | ~16 μs |
| `apply_config_defaults` | 1 | ~2 μs |
| `ExecutionConfig.__post_init__` | 1 | ~2 μs (first call only walks stack) |
| `_warnings.warn` | **0** | removed from hot path |

## Fixes implemented

1. **`praisonaiagents/config/feature_configs.py`** — Fix `ExecutionConfig.__post_init__` deprecation guard; cache internal SDK detection.
2. **`praisonaiagents/utils/deprecation.py`** — Warn once per process for deprecated params.
3. **`praisonaiagents/config/loader.py`** — Skip `apply_config_defaults` lookups when config has no defaults.
4. **`praisonaiagents/agent/agent.py`** — Lazy LoopGuard, lazy LLM instance, deferred LiteLLM params.
5. **`benchmarks/simple_benchmark.py`** — Use `model=`, add 10-iteration warmup.
6. **`benchmarks/performance_benchmark.py`** — Use `model=` instead of deprecated `llm=`.

## Remaining gap (~16 μs vs ~3 μs)

The residual ~13 μs is primarily **`Agent.__init__` size** (~1200 lines of consolidated config resolution added since v0.1.5). Further optimisation requires a dedicated slim fast-path for `Agent(name=..., output="silent")` without full config object churn.

## How to reproduce

```bash
cd praisonai-agents
PYTHONWARNINGS='ignore::DeprecationWarning' python benchmarks/simple_benchmark.py
PYTHONWARNINGS='ignore::DeprecationWarning' python benchmarks/performance_benchmark.py
```
