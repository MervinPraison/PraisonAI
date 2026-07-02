#!/usr/bin/env bash
# C7 import-direction gate for praisonai-code (standalone hot path).
set -euo pipefail

ROOT="${1:-src/praisonai-code/praisonai_code}"
cd "$(dirname "$0")/.."

# Module-level hot path: praisonai wrapper only (not praisonaiagents / praisonai_code).
HOT_PATH_RE='^from praisonai([[:space:]]|\.|$)|^import praisonai([[:space:]]|\.|$)'
# Line-level wrapper imports (exclude praisonaiagents, praisonai_code, praisonai-tools).
ANY_WRAPPER_RE='(^\s*from praisonai\.|^import praisonai($|\.))'
ALLOWLIST="scripts/c7_wrapper_import_allowlist.txt"

echo "== C7 hot-path module-level gate =="
for f in \
  "$ROOT/cli/main.py" \
  "$ROOT/cli/app.py" \
  "$ROOT/cli/commands/run.py" \
  "$ROOT/cli/commands/chat.py" \
  "$ROOT/cli/commands/code.py"
do
  if grep -E "$HOT_PATH_RE" "$f" 2>/dev/null; then
    echo "FAIL: module-level wrapper import in $f"
    exit 1
  fi
done
echo "hot-path module-level gate ok"

echo "== C7 strict gate (run/chat/code/app — no wrapper imports) =="
for f in \
  "$ROOT/cli/app.py" \
  "$ROOT/cli/commands/run.py" \
  "$ROOT/cli/commands/chat.py" \
  "$ROOT/cli/commands/code.py"
do
  if grep -E "$ANY_WRAPPER_RE" "$f" 2>/dev/null; then
    echo "FAIL: wrapper import in $f"
    exit 1
  fi
done
echo "strict hot-path gate ok"

echo "== C7 regression baseline (total wrapper import lines) =="
BASELINE="${C7_WRAPPER_IMPORT_BASELINE:-211}"
COUNT="$(rg -c "$ANY_WRAPPER_RE" "$ROOT" --glob '*.py' 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')"
echo "wrapper import lines: $COUNT (baseline $BASELINE)"
if [ "$COUNT" -gt "$BASELINE" ]; then
  echo "FAIL: wrapper import count regressed above baseline ($COUNT > $BASELINE)"
  exit 1
fi
echo "regression baseline ok"

if [ -f "$ALLOWLIST" ]; then
  echo "== C7 allowlist present: $ALLOWLIST =="
fi
