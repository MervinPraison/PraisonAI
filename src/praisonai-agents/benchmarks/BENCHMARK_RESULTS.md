# PraisonAI Agents - Benchmark Results

**Generated:** 2026-10-15 (single run of `performance_benchmark.py`)
**Methodology:** 10 warmup runs + 1000 measured iterations per framework
**Setup (every framework):** one agent, model `gpt-4o-mini`, one `get_weather` tool, no LLM call. Tool wrapping (`function_tool`, `@tool`, ...) happens inside the timed call. Frameworks that were not installed are omitted.

## Agent Instantiation Time

| Framework | Avg (μs) | Min (μs) | Median (μs) | Std (μs) | Avg memory (KiB) | Relative |
|-----------|----------|----------|-------------|----------|------------------|----------|
| Agno | 9.51 | 9.16 | 9.33 | 1.00 | 6.83 | 1.00x (fastest) |
| PraisonAI | 45.55 | 42.63 | 44.26 | 4.11 | 20.55 | 4.79x |
| PraisonAI (LiteLLM) | 46.94 | 44.65 | 45.82 | 3.26 | 20.81 | 4.94x |
| OpenAI Agents SDK | 591.02 | 529.26 | 566.69 | 60.62 | 60.19 | 62.18x |
| PydanticAI | 1,021.99 | 882.02 | 935.63 | 1,674.03 | 51.22 | 108x |
| LangGraph | 3,232.91 | 2,836.27 | 3,183.02 | 233.32 | 89.66 | 340x |

## Package Versions

| Package | Version |
|---------|---------|
| praisonaiagents | 1.7.12 |
| agno | 3.1.3 |
| pydantic-ai-slim | 2.56.0 |
| openai-agents | 0.23.1 |
| langgraph | 1.2.15 |

## Machine

| Field | Value |
|-------|-------|
| Platform | Linux-6.17.0-1022-azure-x86_64-with-glibc2.39 |
| Processor | x86_64 |
| CPUs | 4 |
| Python | 3.12.3 |
| Load avg (1 min) at start | 0.85 |

## How to Reproduce

```bash
cd src/praisonai-agents
pip install -e . agno openai-agents "pydantic-ai-slim[openai]" langgraph langchain-openai crewai
# OpenAI-backed constructors need a key to exist; no request is made
OPENAI_API_KEY=sk-dummy PYTHONWARNINGS='ignore::DeprecationWarning' python benchmarks/performance_benchmark.py --save
```

Older, superseded result files live in [`archive/`](archive/).
