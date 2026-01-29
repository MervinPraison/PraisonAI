#!/usr/bin/env bash
set -euo pipefail

INSTALL_URL="${PRAISONAI_INSTALL_URL:-https://praison.ai/install.sh}"
EXPECTED_VERSION="${PRAISONAI_EXPECTED_VERSION:-}"
EXTRAS="${PRAISONAI_EXTRAS:-}"

echo "==> PraisonAI Install Smoke Test"
echo "install_url=$INSTALL_URL"
echo "expected_version=$EXPECTED_VERSION"
echo "extras=$EXTRAS"

# Get latest version from PyPI if not specified
if [[ -z "$EXPECTED_VERSION" ]]; then
  echo "==> Fetching latest version from PyPI..."
  EXPECTED_VERSION=$(pip index versions praisonaiagents 2>/dev/null | head -1 | grep -oP '\(\K[^)]+' || echo "")
  if [[ -z "$EXPECTED_VERSION" ]]; then
    # Fallback: try pip show after install
    echo "==> Could not determine version from PyPI, will verify after install"
  fi
fi

echo "==> Running official installer one-liner"
if [[ -n "$EXTRAS" ]]; then
  PRAISONAI_EXTRAS="$EXTRAS" curl -fsSL "$INSTALL_URL" | bash
else
  curl -fsSL "$INSTALL_URL" | bash
fi

echo "==> Verify installation"

# Source the venv if it exists
VENV_DIR="$HOME/.praisonai/venv"
if [[ -d "$VENV_DIR" ]]; then
  source "$VENV_DIR/bin/activate"
fi

# Check import works
python3 -c "import praisonaiagents; print(f'Installed version: {praisonaiagents.__version__}')"

INSTALLED_VERSION=$(python3 -c "import praisonaiagents; print(praisonaiagents.__version__)" 2>/dev/null)
echo "installed=$INSTALLED_VERSION expected=$EXPECTED_VERSION"

if [[ -n "$EXPECTED_VERSION" && "$INSTALLED_VERSION" != "$EXPECTED_VERSION" ]]; then
  echo "WARNING: Version mismatch (expected $EXPECTED_VERSION, got $INSTALLED_VERSION)"
  # Don't fail on version mismatch for now, as PyPI version detection may be flaky
fi

echo "==> Sanity check: Basic agent creation"
python3 -c "
from praisonaiagents import Agent
agent = Agent(name='test', instructions='You are a test agent')
print(f'Agent created: {agent.name}')
print('Basic sanity check passed!')
"

echo "==> Smoke test PASSED"
