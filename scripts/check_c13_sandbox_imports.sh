#!/usr/bin/env bash
# C13 import-direction gate for praisonai-sandbox.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CODE_ROOT="${C13_CODE_ROOT:-src/praisonai-code/praisonai_code}"
AGENTS_ROOT="${C13_AGENTS_ROOT:-src/praisonai-agents/praisonaiagents}"
SANDBOX_ROOT="${C13_SANDBOX_ROOT:-src/praisonai-sandbox/praisonai_sandbox}"

ANY_WRAPPER_RE='(^[[:space:]]*from praisonai([[:space:]]|\.)|^[[:space:]]*import praisonai($|\.))'
ANY_CODE_RE='(^from praisonai_code([[:space:]]|\.)|^import praisonai_code($|\.))'
ANY_SANDBOX_RE='(^[[:space:]]*from praisonai_sandbox([[:space:]]|\.)|^[[:space:]]*import praisonai_sandbox($|\.))'

echo "== C13 praisonai_sandbox wrapper import gate (must be zero outside bridges) =="
if command -v rg >/dev/null 2>&1; then
  MATCHES="$(rg -n "$ANY_WRAPPER_RE" "$SANDBOX_ROOT" --glob '*.py' 2>/dev/null | grep -v '_wrapper_bridge.py' | grep -v '_bootstrap.py' | grep -v '_code_bridge.py' || true)"
else
  MATCHES="$(grep -rEn --include='*.py' "$ANY_WRAPPER_RE" "$SANDBOX_ROOT" 2>/dev/null | grep -v '_wrapper_bridge.py' | grep -v '_bootstrap.py' | grep -v '_code_bridge.py' || true)"
fi
if [ -n "$MATCHES" ]; then
  echo "$MATCHES"
  echo "FAIL: praisonai_sandbox imports the praisonai wrapper"
  exit 1
fi
echo "sandbox wrapper import gate ok"

echo "== C13 praisonai_sandbox module-level praisonai_code import gate =="
if command -v rg >/dev/null 2>&1; then
  MATCHES="$(rg -n "$ANY_CODE_RE" "$SANDBOX_ROOT" --glob '*.py' 2>/dev/null | grep -v '_code_bridge.py' | grep -v '_registry.py' || true)"
else
  MATCHES="$(grep -rEn --include='*.py' "$ANY_CODE_RE" "$SANDBOX_ROOT" 2>/dev/null | grep -v '_code_bridge.py' | grep -v '_registry.py' || true)"
fi
if [ -n "$MATCHES" ]; then
  echo "$MATCHES"
  echo "FAIL: module-level praisonai_code import in praisonai_sandbox"
  exit 1
fi
echo "sandbox code import gate ok"

echo "== C13 praisonaiagents hot-path gate (no praisonai_sandbox at module level) =="
for f in \
  "$AGENTS_ROOT/sandbox/manager.py" \
  "$AGENTS_ROOT/sandbox/protocols.py" \
  "$AGENTS_ROOT/sandbox/config.py"
do
  if [ -f "$f" ] && head -n 80 "$f" | grep -E "$ANY_SANDBOX_RE" 2>/dev/null; then
    echo "FAIL: module-level praisonai_sandbox import in agents hot path $f"
    exit 1
  fi
done
echo "agents hot-path gate ok"

echo "== C13 praisonai-code hot-path gate (no praisonai_sandbox at module level) =="
for f in \
  "$CODE_ROOT/cli/main.py" \
  "$CODE_ROOT/cli/app.py" \
  "$CODE_ROOT/cli/commands/run.py" \
  "$CODE_ROOT/cli/commands/chat.py" \
  "$CODE_ROOT/cli/commands/code.py"
do
  if [ -f "$f" ] && head -n 80 "$f" | grep -E "$ANY_SANDBOX_RE" 2>/dev/null; then
    echo "FAIL: module-level praisonai_sandbox import in code hot path $f"
    exit 1
  fi
done
echo "code hot-path gate ok"

echo "C13 import gates passed"
