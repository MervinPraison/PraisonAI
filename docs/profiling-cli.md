# Profiling CLI

PraisonAI provides unified profiling capabilities for performance analysis and debugging.

## Quick Start

```bash
# Basic profiling
praisonai "What is 2+2?" --profile

# Deep profiling with call graph
praisonai "What is 2+2?" --profile --profile-deep

# JSON output format
praisonai "What is 2+2?" --profile --profile-format json
```

## CLI Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--profile` | Enable profiling with timing breakdown | Disabled |
| `--profile-deep` | Enable deep profiling with call graph (higher overhead) | Disabled |
| `--profile-format` | Output format: `text` or `json` | `text` |

## Profile Command

For more detailed profiling options, use the `profile` subcommand:

```bash
# Profile a query
praisonai profile query "What is 2+2?"

# With deep call tracing
praisonai profile query "Hello" --deep

# Limit functions shown
praisonai profile query "Test" --limit 20

# Save artifacts to directory
praisonai profile query "Test" --save ./profile_results

# JSON output
praisonai profile query "Test" --format json
```

### Profile Query Options

| Option | Description | Default |
|--------|-------------|---------|
| `--model, -m` | Model to use | Default model |
| `--stream/--no-stream` | Use streaming mode | No stream |
| `--deep` | Enable deep call tracing | Disabled |
| `--limit, -n` | Top N functions to show | 30 |
| `--sort, -s` | Sort by: `cumulative` or `tottime` | `cumulative` |
| `--show-callers` | Show caller functions | Disabled |
| `--show-callees` | Show callee functions | Disabled |
| `--save` | Save artifacts to path | None |
| `--format, -f` | Output format: `text` or `json` | `text` |

## Other Profile Commands

```bash
# Profile module import times
praisonai profile imports

# Profile CLI startup time
praisonai profile startup

# Run comprehensive profiling suite
praisonai profile suite

# Create performance snapshots for comparison
praisonai profile snapshot --baseline
praisonai profile snapshot current --compare

# Configure performance optimizations
praisonai profile optimize --show
```

## Output Format

### Text Report

```
======================================================================
PraisonAI Profile Report
======================================================================

Run ID:     abc12345
Timestamp:  2024-01-02T12:00:00.000000Z
Method:     cli_direct
Version:    3.0.1

## Timing Breakdown
----------------------------------------
  Imports:            500.00 ms
  Agent Init:           0.50 ms
  Execution:         2000.00 ms
  ─────────────────────────────────────
  TOTAL:             2500.50 ms

## Top Functions by Cumulative Time
----------------------------------------------------------------------
Function                                    Calls   Cumul (ms)
----------------------------------------------------------------------
request                                         1      1800.00
send                                            1      1750.00
...
```

### JSON Report

```json
{
  "schema_version": "1.0",
  "run_id": "abc12345",
  "timestamp": "2024-01-02T12:00:00.000000Z",
  "invocation": {
    "method": "cli_direct",
    "flags": {"layer": 1, "stream": false, "model": null},
    "praisonai_version": "3.0.1",
    "python_version": "3.12.0"
  },
  "timing": {
    "total_ms": 2500.5,
    "imports_ms": 500.0,
    "agent_init_ms": 0.5,
    "execution_ms": 2000.0
  },
  "functions": [...],
  "response_preview": "four"
}
```

## Profiling Layers

| Layer | Overhead | Features |
|-------|----------|----------|
| 0 | < 1ms | Wall-clock phases only |
| 1 | ~5% | + cProfile function stats |
| 2 | ~15% | + Call graph (callers/callees) |

- `--profile` uses Layer 1
- `--profile --profile-deep` uses Layer 2

## Performance Tips

1. **Use Layer 0 for production monitoring** - minimal overhead
2. **Use Layer 1 for development profiling** - good balance
3. **Use Layer 2 only for deep debugging** - higher overhead

## Observational Equivalence

The following commands produce equivalent profile reports:

```bash
# CLI direct
praisonai "prompt" --profile

# Profile command
praisonai profile query "prompt"
```

Both use the same unified profiling architecture and produce identical schema output.
