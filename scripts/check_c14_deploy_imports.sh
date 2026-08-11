#!/usr/bin/env bash
# C14 import-direction gate for praisonai-deploy.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CODE_ROOT="${C14_CODE_ROOT:-src/praisonai-code/praisonai_code}"
DEPLOY_ROOT="${C14_DEPLOY_ROOT:-src/praisonai-deploy/praisonai_deploy}"

ANY_WRAPPER_RE='(^[[:space:]]*from praisonai([[:space:]]|\.)|^[[:space:]]*import praisonai($|\.))'
ANY_CODE_RE='(^from praisonai_code([[:space:]]|\.)|^import praisonai_code($|\.))'
ANY_DEPLOY_RE='(^[[:space:]]*from praisonai_deploy([[:space:]]|\.)|^[[:space:]]*import praisonai_deploy($|\.))'

echo "== C14 praisonai_deploy wrapper import gate (must be zero outside bridges) =="
if command -v rg >/dev/null 2>&1; then
  MATCHES="$(rg -n "$ANY_WRAPPER_RE" "$DEPLOY_ROOT" --glob '*.py' 2>/dev/null | grep -v '_wrapper_bridge.py' | grep -v '_bootstrap.py' | grep -v '_code_bridge.py' || true)"
else
  MATCHES="$(grep -rEn --include='*.py' "$ANY_WRAPPER_RE" "$DEPLOY_ROOT" 2>/dev/null | grep -v '_wrapper_bridge.py' | grep -v '_bootstrap.py' | grep -v '_code_bridge.py' || true)"
fi
if [ -n "$MATCHES" ]; then
  echo "$MATCHES"
  echo "FAIL: praisonai_deploy imports the praisonai wrapper"
  exit 1
fi
echo "deploy wrapper import gate ok"

echo "== C14 praisonai_deploy module-level praisonai_code import gate =="
if command -v rg >/dev/null 2>&1; then
  MATCHES="$(rg -n "$ANY_CODE_RE" "$DEPLOY_ROOT" --glob '*.py' 2>/dev/null | grep -v '_code_bridge.py' | grep -v '_plugin_registry.py' || true)"
else
  MATCHES="$(grep -rEn --include='*.py' "$ANY_CODE_RE" "$DEPLOY_ROOT" 2>/dev/null | grep -v '_code_bridge.py' | grep -v '_plugin_registry.py' || true)"
fi
if [ -n "$MATCHES" ]; then
  echo "$MATCHES"
  echo "FAIL: module-level praisonai_code import in praisonai_deploy"
  exit 1
fi
echo "deploy code import gate ok"

echo "== C14 praisonai-code hot-path gate (no praisonai_deploy at module level) =="
for f in \
  "$CODE_ROOT/cli/main.py" \
  "$CODE_ROOT/cli/app.py" \
  "$CODE_ROOT/cli/commands/run.py" \
  "$CODE_ROOT/cli/commands/chat.py" \
  "$CODE_ROOT/cli/commands/code.py"
do
  if [ -f "$f" ] && head -n 80 "$f" | grep -E "$ANY_DEPLOY_RE" 2>/dev/null; then
    echo "FAIL: module-level praisonai_deploy import in code hot path $f"
    exit 1
  fi
done
echo "code hot-path gate ok"

echo "C14 import gates passed"
