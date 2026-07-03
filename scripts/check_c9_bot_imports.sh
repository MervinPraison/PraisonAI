#!/usr/bin/env bash
# C9 import-direction gate for praisonai-bot and praisonai-code hot paths.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CODE_ROOT="${C9_CODE_ROOT:-src/praisonai-code/praisonai_code}"
BOT_ROOT="${C9_BOT_ROOT:-src/praisonai-bot/praisonai_bot}"

ANY_WRAPPER_RE='(^[[:space:]]*from praisonai([[:space:]]|\.)|^[[:space:]]*import praisonai($|\.))'
ANY_BOT_RE='(^[[:space:]]*from praisonai_bot([[:space:]]|\.)|^[[:space:]]*import praisonai_bot($|\.))'
CODE_HOT='^from praisonai([[:space:]]|\.|$)|^import praisonai([[:space:]]|\.|$)'
BOT_ALLOWLIST="scripts/c9_wrapper_import_allowlist.txt"

count_wrapper_imports() {
  local root="$1"
  if command -v rg >/dev/null 2>&1; then
    { rg -c "$ANY_WRAPPER_RE" "$root" --glob '*.py' 2>/dev/null || true; } | awk -F: '{s+=$2} END {print s+0}'
  else
    { grep -rEc --include='*.py' "$ANY_WRAPPER_RE" "$root" 2>/dev/null || true; } | awk -F: '{s+=$2} END {print s+0}'
  fi
}

echo "== C9 praisonai-code hot-path gate (no praisonai_bot at module level) =="
for f in \
  "$CODE_ROOT/cli/main.py" \
  "$CODE_ROOT/cli/app.py" \
  "$CODE_ROOT/cli/commands/run.py" \
  "$CODE_ROOT/cli/commands/chat.py" \
  "$CODE_ROOT/cli/commands/code.py"
do
  if [ -f "$f" ] && head -n 80 "$f" | grep -E "$CODE_HOT" 2>/dev/null; then
    echo "FAIL: module-level wrapper import in $f"
    exit 1
  fi
  if [ -f "$f" ] && head -n 80 "$f" | grep -E "$ANY_BOT_RE" 2>/dev/null; then
    echo "FAIL: module-level praisonai_bot import in code hot path $f"
    exit 1
  fi
done
echo "code hot-path gate ok"

echo "== C9 praisonai-bot wrapper import regression =="
BASELINE="${C9_WRAPPER_IMPORT_BASELINE:-20}"
COUNT="$(count_wrapper_imports "$BOT_ROOT")"
echo "wrapper import lines in praisonai_bot: $COUNT (baseline $BASELINE)"
if [ "$COUNT" -gt "$BASELINE" ]; then
  echo "FAIL: praisonai_bot wrapper import count $COUNT > $BASELINE"
  exit 1
fi
echo "bot wrapper import baseline ok"

echo "C9 import gates passed"
