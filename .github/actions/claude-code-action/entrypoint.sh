#!/bin/sh

set -e

echo "Running Claude Code in CI mode..."

# Debug environment
echo "Current PATH: $PATH"
echo "Available commands:"
which node || echo "node not found"
which npm || echo "npm not found"
which claude || echo "claude not found"

# Check if claude is installed
if ! command -v claude >/dev/null 2>&1; then
    echo "Error: claude command not found"
    echo "Attempting to install claude..."
    npm install -g @anthropic-ai/claude-code || {
        echo "Failed to install claude"
        exit 1
    }
fi

# Extract GitHub context and create a smart prompt
PROMPT="Analyse the GitHub issue or PR context and generate a smart response based on the repository context."

# Set environment variables from arguments
export ANTHROPIC_API_KEY="${1#--anthropic-api-key=}"
export GITHUB_TOKEN="${2#--github-token=}"

# Debug environment variables
echo "ANTHROPIC_API_KEY set: $([ -n "$ANTHROPIC_API_KEY" ] && echo "yes" || echo "no")"
echo "GITHUB_TOKEN set: $([ -n "$GITHUB_TOKEN" ] && echo "yes" || echo "no")"

# Verify environment variables
if [ -z "$ANTHROPIC_API_KEY" ] || [ -z "$GITHUB_TOKEN" ]; then
    echo "Error: Required environment variables are not set"
    echo "Args received: $@"
    exit 1
fi

# Run Claude with explicit path and avoid env issues
echo "Running claude command..."
exec claude -p "$PROMPT" 