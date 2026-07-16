#!/usr/bin/env bash
# C12 import-direction gate for praisonai-mcp.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CODE_ROOT="${C12_CODE_ROOT:-src/praisonai-code/praisonai_code}"
MCP_ROOT="${C12_MCP_ROOT:-src/praisonai-mcp/praisonai_mcp}"

ANY_WRAPPER_RE='(^[[:space:]]*from praisonai([[:space:]]|\.)|^[[:space:]]*import praisonai($|\.))'
ANY_CODE_RE='(^from praisonai_code([[:space:]]|\.)|^import praisonai_code($|\.))'
ANY_MCP_RE='(^[[:space:]]*from praisonai_mcp([[:space:]]|\.)|^[[:space:]]*import praisonai_mcp($|\.))'

echo "== C12 praisonai_mcp wrapper import gate (must be zero outside bridges) =="
if command -v rg >/dev/null 2>&1; then
  MATCHES="$(rg -n "$ANY_WRAPPER_RE" "$MCP_ROOT" --glob '*.py' 2>/dev/null | grep -v '_wrapper_bridge.py' | grep -v '_bootstrap.py' | grep -v '_code_bridge.py' || true)"
else
  MATCHES="$(grep -rEn --include='*.py' "$ANY_WRAPPER_RE" "$MCP_ROOT" 2>/dev/null | grep -v '_wrapper_bridge.py' | grep -v '_bootstrap.py' | grep -v '_code_bridge.py' || true)"
fi
if [ -n "$MATCHES" ]; then
  echo "$MATCHES"
  echo "FAIL: praisonai_mcp imports the praisonai wrapper"
  exit 1
fi
echo "mcp wrapper import gate ok"

echo "== C12 praisonai_mcp module-level praisonai_code import gate =="
if command -v rg >/dev/null 2>&1; then
  MATCHES="$(rg -n "$ANY_CODE_RE" "$MCP_ROOT" --glob '*.py' 2>/dev/null | grep -v '_code_bridge.py' | grep -v 'cli/_configuration.py' | grep -v 'cli/output/console.py' || true)"
else
  MATCHES="$(grep -rEn --include='*.py' "$ANY_CODE_RE" "$MCP_ROOT" 2>/dev/null | grep -v '_code_bridge.py' | grep -v 'cli/_configuration.py' | grep -v 'cli/output/console.py' || true)"
fi
if [ -n "$MATCHES" ]; then
  echo "$MATCHES"
  echo "FAIL: module-level praisonai_code import in praisonai_mcp"
  exit 1
fi
echo "mcp code import gate ok"

echo "== C12 praisonai-code hot-path gate (no praisonai_mcp at module level) =="
for f in \
  "$CODE_ROOT/cli/main.py" \
  "$CODE_ROOT/cli/app.py" \
  "$CODE_ROOT/cli/commands/run.py" \
  "$CODE_ROOT/cli/commands/chat.py" \
  "$CODE_ROOT/cli/commands/code.py"
do
  if [ -f "$f" ] && head -n 80 "$f" | grep -E "$ANY_MCP_RE" 2>/dev/null; then
    echo "FAIL: module-level praisonai_mcp import in code hot path $f"
    exit 1
  fi
done
echo "code hot-path gate ok"

echo "C12 import gates passed"
