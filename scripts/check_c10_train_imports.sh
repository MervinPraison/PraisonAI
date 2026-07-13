#!/usr/bin/env bash
# C10 import-direction gate for praisonai-train.
#
# - praisonai_train must not import the praisonai wrapper at module level
#   (standalone `pip install praisonai-train` must work without it).
# - praisonai_train must not import praisonai_code at module level
#   (code access goes through the lazy _code_bridge).
# - praisonai-code hot paths must not import praisonai_train at module level.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CODE_ROOT="${C10_CODE_ROOT:-src/praisonai-code/praisonai_code}"
TRAIN_ROOT="${C10_TRAIN_ROOT:-src/praisonai-train/praisonai_train}"

ANY_WRAPPER_RE='(^[[:space:]]*from praisonai([[:space:]]|\.)|^[[:space:]]*import praisonai($|\.))'
ANY_CODE_RE='(^from praisonai_code([[:space:]]|\.)|^import praisonai_code($|\.))'
ANY_TRAIN_RE='(^[[:space:]]*from praisonai_train([[:space:]]|\.)|^[[:space:]]*import praisonai_train($|\.))'

echo "== C10 praisonai_train wrapper import gate (must be zero) =="
if command -v rg >/dev/null 2>&1; then
  MATCHES="$(rg -n "$ANY_WRAPPER_RE" "$TRAIN_ROOT" --glob '*.py' 2>/dev/null | grep -v 'praisonai_train\|praisonaiagents' || true)"
else
  MATCHES="$(grep -rEn --include='*.py' "$ANY_WRAPPER_RE" "$TRAIN_ROOT" 2>/dev/null | grep -v 'praisonai_train\|praisonaiagents' || true)"
fi
if [ -n "$MATCHES" ]; then
  echo "$MATCHES"
  echo "FAIL: praisonai_train imports the praisonai wrapper"
  exit 1
fi
echo "train wrapper import gate ok"

echo "== C10 praisonai_train module-level praisonai_code import gate =="
# Column-0 imports only: in-function (indented) lazy imports via _code_bridge are allowed.
if command -v rg >/dev/null 2>&1; then
  MATCHES="$(rg -n "$ANY_CODE_RE" "$TRAIN_ROOT" --glob '*.py' 2>/dev/null || true)"
else
  MATCHES="$(grep -rEn --include='*.py' "$ANY_CODE_RE" "$TRAIN_ROOT" 2>/dev/null || true)"
fi
if [ -n "$MATCHES" ]; then
  echo "$MATCHES"
  echo "FAIL: module-level praisonai_code import in praisonai_train"
  exit 1
fi
echo "train code import gate ok"

echo "== C10 praisonai-code hot-path gate (no praisonai_train at module level) =="
for f in \
  "$CODE_ROOT/cli/main.py" \
  "$CODE_ROOT/cli/app.py" \
  "$CODE_ROOT/cli/commands/run.py" \
  "$CODE_ROOT/cli/commands/chat.py" \
  "$CODE_ROOT/cli/commands/code.py"
do
  if [ -f "$f" ] && head -n 80 "$f" | grep -E "$ANY_TRAIN_RE" 2>/dev/null; then
    echo "FAIL: module-level praisonai_train import in code hot path $f"
    exit 1
  fi
done
echo "code hot-path gate ok"

echo "C10 import gates passed"
