# EvaluationLoop Examples

Examples demonstrating iterative evaluation and improvement patterns.

## Quick Start

```bash
pip install praisonaiagents
export OPENAI_API_KEY=your-key
```

## Examples

| File | Description |
|------|-------------|
| `basic_evaluation_loop.py` | Simple loop: Run → Judge → Improve |
| `multi_step_task_loop.py` | Sequential tasks with context passing |
| `recipe_optimization_loop.py` | CLI-based recipe optimization |

## Pattern

```
┌─────────┐     ┌─────────┐     ┌──────────┐
│  Agent  │ ──► │  Judge  │ ──► │ Feedback │
│  runs   │     │ scores  │     │ improves │
└─────────┘     └─────────┘     └──────────┘
     ▲                               │
     └───────────────────────────────┘
           (repeat until 8.0+)
```

## Run Examples

```bash
# Basic loop
python basic_evaluation_loop.py

# Multi-step with context
python multi_step_task_loop.py

# CLI recipe loop
python recipe_optimization_loop.py "research AI trends"
```
