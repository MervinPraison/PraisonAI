#!/usr/bin/env bash
# Fail if praisonai_bot production code imports praisonai.* at module level (outside allowlist).
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="src/praisonai-bot/praisonai_bot"
ALLOWLIST="scripts/c9_wrapper_import_allowlist.txt"
RE='^(from praisonai\.|import praisonai\.)'
FAIL=0
while IFS= read -r f; do
  rel="${f#"$ROOT/"}"
  if printf '%s\n' "$(sed -E 's/[[:space:]]*#.*$//;/^[[:space:]]*$/d' "$ALLOWLIST")" | grep -Fxq "$rel"; then
    continue
  fi
  if grep -E "$RE" "$f" 2>/dev/null | grep -v '^[[:space:]]*#'; then
    echo "FAIL: module-level praisonai import in $rel"
    FAIL=1
  fi
done < <(find "$ROOT" -name '*.py' -type f)
[ "$FAIL" -eq 0 ] && echo "audit_bot_wrapper_imports ok" || exit 1
