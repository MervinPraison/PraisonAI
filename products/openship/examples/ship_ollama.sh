#!/usr/bin/env bash
# Run inside a Git working tree with an edit, after installing praisonai-code.
set -euo pipefail

# Start Ollama before running this example. The initial pull needs a connection.
ollama pull qwen3.5:9b
praisonai-code ship review --dry-run
praisonai-code ship review --model ollama/qwen3.5:9b --effort low
