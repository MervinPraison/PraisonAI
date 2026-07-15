#!/usr/bin/env bash
# C11 import-direction gate for praisonai-browser.
#
# - praisonai_browser must not import the praisonai wrapper at module level
#   (standalone `pip install praisonai-browser` must work without it).
# - praisonai_browser must not import praisonai_code at module level.
# - praisonai-code hot paths must not import praisonai_browser at module level.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CODE_ROOT="${C11_CODE_ROOT:-src/praisonai-code/praisonai_code}"
BROWSER_ROOT="${C11_BROWSER_ROOT:-src/praisonai-browser/praisonai_browser}"

ANY_WRAPPER_RE='(^[[:space:]]*from praisonai([[:space:]]|\.)|^[[:space:]]*import praisonai($|\.))'
ANY_CODE_RE='(^from praisonai_code([[:space:]]|\.)|^import praisonai_code($|\.))'
ANY_BROWSER_RE='(^[[:space:]]*from praisonai_browser([[:space:]]|\.)|^[[:space:]]*import praisonai_browser($|\.))'

echo "== C11 praisonai_browser wrapper import gate (must be zero) =="
if command -v rg >/dev/null 2>&1; then
  MATCHES="$(rg -n "$ANY_WRAPPER_RE" "$BROWSER_ROOT" --glob '*.py' 2>/dev/null | grep -Ev 'praisonai_browser|praisonaiagents' || true)"
else
  MATCHES="$(grep -rEn --include='*.py' "$ANY_WRAPPER_RE" "$BROWSER_ROOT" 2>/dev/null | grep -Ev 'praisonai_browser|praisonaiagents' || true)"
fi
if [ -n "$MATCHES" ]; then
  echo "$MATCHES"
  echo "FAIL: praisonai_browser imports the praisonai wrapper"
  exit 1
fi
echo "browser wrapper import gate ok"

echo "== C11 praisonai_browser module-level praisonai_code import gate =="
if command -v rg >/dev/null 2>&1; then
  MATCHES="$(rg -n "$ANY_CODE_RE" "$BROWSER_ROOT" --glob '*.py' 2>/dev/null || true)"
else
  MATCHES="$(grep -rEn --include='*.py' "$ANY_CODE_RE" "$BROWSER_ROOT" 2>/dev/null || true)"
fi
if [ -n "$MATCHES" ]; then
  echo "$MATCHES"
  echo "FAIL: module-level praisonai_code import in praisonai_browser"
  exit 1
fi
echo "browser code import gate ok"

echo "== C11 praisonai-code hot-path gate (no praisonai_browser at module level) =="
for f in \
  "$CODE_ROOT/cli/main.py" \
  "$CODE_ROOT/cli/app.py" \
  "$CODE_ROOT/cli/commands/run.py" \
  "$CODE_ROOT/cli/commands/chat.py" \
  "$CODE_ROOT/cli/commands/code.py"
do
  if [ -f "$f" ] && head -n 80 "$f" | grep -E "$ANY_BROWSER_RE" 2>/dev/null; then
    echo "FAIL: module-level praisonai_browser import in code hot path $f"
    exit 1
  fi
done
echo "code hot-path gate ok"

echo "C11 import gates passed"
