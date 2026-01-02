# Profiling CLI

PraisonAI provides unified profiling capabilities for performance analysis and debugging, with **full visibility from ENTER to first response**.

## Quick Start

```bash
# Basic profiling
praisonai "What is 2+2?" --profile

# Deep profiling with call graph, decision trace, and module breakdown
praisonai "What is 2+2?" --profile --profile-deep

# JSON output format
praisonai "What is 2+2?" --profile --profile-format json
```

## Time to First Response (TTFR)

**TTFR** is the key user-perceived latency metric. It measures the time from when you press ENTER until the first visible output appears.

### What contributes to TTFR?

1. **CLI Entry** - Time to reach the CLI entry point
2. **CLI Parse** - Argparse/Typer routing time
3. **Routing** - Command routing to handler
4. **Imports** - Loading required modules
5. **Agent Init** - Initializing the agent
6. **Network Request** - Sending request to LLM API
7. **First Token** - Receiving first token (streaming)
8. **First Output** - Rendering first visible output

### How to reduce TTFR

1. **Warm runs** - Imports are cached after first run
2. **Streaming mode** - See output as tokens arrive
3. **Lighter models** - Faster response times
4. **Local models** - Eliminate network latency

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

## Execution Timeline
---------------------------------------------
  Imports                   :   500.00 ms
  Agent Init                :     0.50 ms
  Execution                 :  2000.00 ms
  ───────────────────────────────────────────
  ⏱ Time to First Response  :  2500.50 ms
  TOTAL                     :  2500.50 ms

## Timing Breakdown
----------------------------------------
  Imports:            500.00 ms
  Agent Init:           0.50 ms
  Execution:         2000.00 ms
  ─────────────────────────────────────
  TOTAL:             2500.50 ms

## Decision Trace (deep profile only)
----------------------------------------
  Agent Config:    default
  Model:           gpt-4
  Streaming:       disabled
  Profile Layer:   2

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
