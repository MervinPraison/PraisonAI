#!/bin/bash
# CI script for standardisation checks
# Usage: ./scripts/standardise_check.sh [--strict]
#
# Exit codes:
#   0 - No issues found
#   1 - Issues found
#   2 - Error running check

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Check if strict mode
STRICT_MODE=false
if [[ "$1" == "--strict" ]]; then
    STRICT_MODE=true
fi

echo "🔍 Running PraisonAI Standardisation Check..."
echo ""

# Run the check
cd "$PROJECT_ROOT"
python -m praisonai.cli.commands.standardise check --ci --path "$PROJECT_ROOT"
EXIT_CODE=$?

if [[ $EXIT_CODE -eq 0 ]]; then
    echo ""
    echo "✅ Standardisation check passed!"
    exit 0
elif [[ $EXIT_CODE -eq 1 ]]; then
    echo ""
    echo "⚠️  Standardisation issues found."
    if [[ "$STRICT_MODE" == "true" ]]; then
        echo "Failing in strict mode."
        exit 1
    else
        echo "Run 'praisonai standardise report' for details."
        exit 0  # Non-strict mode: warn but don't fail
    fi
else
    echo ""
    echo "❌ Error running standardisation check."
    exit 2
fi
