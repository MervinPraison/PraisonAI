# Run History Example

This example demonstrates how to use PraisonAI run history for storing, querying, and exporting recipe runs.

## Features Demonstrated

- Storing run results with input/output data
- Listing and filtering runs
- Querying run details
- Exporting runs for replay/debugging
- Storage statistics and cleanup

## Quick Start

```bash
python run_history_example.py
```

## CLI Commands

```bash
# List recent runs
praisonai recipe runs list

# List runs for a specific recipe
praisonai recipe runs list --recipe support-reply

# Get storage stats
praisonai recipe runs stats

# Export a run
praisonai recipe export run-abc123 -o export.json

# Replay a run
praisonai recipe replay export.json --compare

# Cleanup old runs
praisonai recipe runs cleanup
```

## Default Storage Location

Run history is stored at `~/.praison/runs`.
