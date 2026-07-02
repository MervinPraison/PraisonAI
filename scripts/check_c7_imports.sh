#!/usr/bin/env bash
# C7 import-direction gate for praisonai-code (standalone hot path).
set -euo pipefail

ROOT="${1:-src/praisonai-code/praisonai_code}"
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Module-level hot path: praisonai wrapper only (not praisonaiagents / praisonai_code).
HOT_PATH_RE='^from praisonai([[:space:]]|\.|$)|^import praisonai([[:space:]]|\.|$)'
# Line-level wrapper imports (exclude praisonaiagents, praisonai_code, praisonai-tools).
# Count indented bare ``import praisonai`` as well (C8.1 regex fix).
ANY_WRAPPER_RE='(^[[:space:]]*from praisonai([[:space:]]|\.)|^[[:space:]]*import praisonai($|\.))'
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
BASELINE="${C8_WRAPPER_IMPORT_BASELINE:-${C7_WRAPPER_IMPORT_BASELINE:-50}}"
# Count wrapper import lines with a portable tool. Prefer ripgrep when present
# (fast, respects the same regex) and fall back to POSIX grep -r otherwise, so
# the gate does not exit 127 on runners without rg. The `|| true` keeps a
# no-match (grep/rg exit 1) from aborting the script under `set -o pipefail`.
if command -v rg >/dev/null 2>&1; then
  COUNT="$( { rg -c "$ANY_WRAPPER_RE" "$ROOT" --glob '*.py' 2>/dev/null || true; } | awk -F: '{s+=$2} END {print s+0}')"
else
  COUNT="$( { grep -rEc --include='*.py' "$ANY_WRAPPER_RE" "$ROOT" 2>/dev/null || true; } | awk -F: '{s+=$2} END {print s+0}')"
fi
echo "wrapper import lines: $COUNT (baseline $BASELINE)"
if [ "$COUNT" -gt "$BASELINE" ]; then
  echo "FAIL: wrapper import count regressed above baseline ($COUNT > $BASELINE)"
  exit 1
fi
echo "regression baseline ok"

echo "== C7 allowlist enforcement =="
if [ -f "$ALLOWLIST" ]; then
  # Files (relative to $ROOT) that carry wrapper imports.
  if command -v rg >/dev/null 2>&1; then
    OFFENDERS="$( { rg -l "$ANY_WRAPPER_RE" "$ROOT" --glob '*.py' 2>/dev/null || true; } )"
  else
    OFFENDERS="$( { grep -rlE --include='*.py' "$ANY_WRAPPER_RE" "$ROOT" 2>/dev/null || true; } )"
  fi
  # Strip the reasons/comments and blank/comment lines from the allowlist.
  ALLOWED="$(sed -E 's/[[:space:]]*#.*$//; /^[[:space:]]*$/d' "$ALLOWLIST" | sed -E 's/[[:space:]]+$//')"
  FAIL=0
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    rel="${f#"$ROOT/"}"
    if ! printf '%s\n' "$ALLOWED" | grep -Fxq "$rel"; then
      echo "FAIL: non-allowlisted wrapper import in $rel (add to $ALLOWLIST after review)"
      FAIL=1
    fi
  done <<< "$OFFENDERS"
  if [ "$FAIL" -ne 0 ]; then
    exit 1
  fi
  echo "allowlist enforcement ok"
else
  echo "allowlist file missing: $ALLOWLIST (skipping enforcement)"
fi
