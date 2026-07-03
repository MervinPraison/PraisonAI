#!/usr/bin/env bash
# C8.4 line-count ratchet for praisonai_code/cli/main.py
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAIN_PY="${1:-$ROOT/src/praisonai-code/praisonai_code/cli/main.py}"
MAX_LINES="${MAX_MAIN_PY_LINES:-300}"

if [[ ! -f "$MAIN_PY" ]]; then
  echo "ERROR: $MAIN_PY not found" >&2
  exit 1
fi

LINES=$(wc -l < "$MAIN_PY" | tr -d ' ')
echo "main.py line count: $LINES (max: $MAX_LINES)"

if [[ "$LINES" -gt "$MAX_LINES" ]]; then
  echo "FAIL: main.py exceeds $MAX_LINES lines ($LINES)" >&2
  exit 1
fi

echo "OK: main.py within limit"
