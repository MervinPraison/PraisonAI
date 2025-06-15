#!/bin/sh

set -e

echo "Running Claude Code in CI mode..."

# Extract GitHub context and create a smart prompt
PROMPT="Analyse the GitHub issue or PR context and generate a smart response based on the repository context."

# Set environment variables
export ANTHROPIC_API_KEY="$1"
export GITHUB_TOKEN="$2"

# Run Claude with the prompt
claude -p "$PROMPT" 