#!/bin/sh

set -e

echo "Running Claude Code in CI mode..."

# Extract GitHub context and create a smart prompt
PROMPT="Analyse the GitHub issue or PR context and generate a smart response based on the repository context."

# Set environment variables from arguments
export ANTHROPIC_API_KEY="${1#--anthropic-api-key=}"
export GITHUB_TOKEN="${2#--github-token=}"

# Verify environment variables
if [ -z "$ANTHROPIC_API_KEY" ] || [ -z "$GITHUB_TOKEN" ]; then
    echo "Error: Required environment variables are not set"
    exit 1
fi

# Run Claude with the prompt
claude -p "$PROMPT" 