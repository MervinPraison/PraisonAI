#!/usr/bin/env bash
# C9 bot→code gate: production code must not hard-import praisonai_code (use _code_bridge).
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="src/praisonai-bot/praisonai_bot"
ALLOWLIST="scripts/c9_code_import_allowlist.txt"
RE='(from praisonai_code|import praisonai_code)'
FAIL=0

allowed_line() {
  local rel="$1"
  if [ ! -f "$ALLOWLIST" ]; then
    return 1
  fi
  sed -E 's/[[:space:]]*#.*$//;/^[[:space:]]*$/d' "$ALLOWLIST" | grep -Fxq "$rel"
}

while IFS= read -r f; do
  rel="${f#"$ROOT/"}"
  if allowed_line "$rel"; then
    continue
  fi
  if grep -E "$RE" "$f" 2>/dev/null | grep -v '^[[:space:]]*#'; then
    echo "FAIL: direct praisonai_code import in $rel (use praisonai_bot._code_bridge)"
    FAIL=1
  fi
done < <(find "$ROOT" -name '*.py' -type f)

if [ "$FAIL" -eq 0 ]; then
  echo "check_bot_code_imports ok"
else
  exit 1
fi
