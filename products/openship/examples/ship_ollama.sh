#!/usr/bin/env bash
# Run OpenShip 100% locally with Ollama — no cloud API key required.
set -euo pipefail

# 1. Make sure Ollama is running and pull a local coding model once:
ollama pull qwen3.5

# 2. Keep cloud keys unset and preview the ship plan first:
unset OPENAI_API_KEY ANTHROPIC_API_KEY
praisonai ship --dry-run --model ollama/qwen3.5

# 3. Commit, self-review, push, and open a draft PR (never merges):
# praisonai ship --post-review --model ollama/qwen3.5
