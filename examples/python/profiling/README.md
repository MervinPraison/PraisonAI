# PraisonAI Profiling Examples

This directory contains examples for profiling PraisonAI agent performance.

## Prerequisites

```bash
pip install praisonai
export OPENAI_API_KEY=your_key_here
```

## Examples

### 1. Basic Profiling (`basic_profiling.py`)

Demonstrates programmatic profiling of a single query:

```bash
python basic_profiling.py
```

### 2. Suite Profiling (`suite_profiling.py`)

Runs a comprehensive profiling suite with multiple scenarios:

```bash
python suite_profiling.py
```

### 3. Optimization Demo (`optimization_example.py`)

Demonstrates Tier 0/1/2 performance optimizations:

```bash
python optimization_example.py
```

## CLI Commands

You can also profile directly from the command line:

```bash
# Profile a query
praisonai profile query "What is 2+2?"

# Profile with file grouping
praisonai profile query "Hello" --show-files --limit 20

# Profile imports
praisonai profile imports

# Profile startup time
praisonai profile startup

# Run comprehensive suite
praisonai profile suite --quick

# Create performance baseline
praisonai profile snapshot --baseline

# Compare against baseline
praisonai profile snapshot current --compare

# Show optimization status
praisonai profile optimize --show
```

## Output

- **Text output**: Human-readable timing breakdown
- **JSON output**: Machine-readable for CI/CD (`--format json`)
- **Artifacts**: Binary cProfile data and reports (`--save ./results`)
- **Snapshots**: Performance baselines for regression detection

## Performance Optimizations

Enable opt-in optimizations via environment variables:

```bash
export PRAISONAI_LITE_MODE=1
export PRAISONAI_SKIP_TYPE_VALIDATION=1
export PRAISONAI_MINIMAL_IMPORTS=1
```
