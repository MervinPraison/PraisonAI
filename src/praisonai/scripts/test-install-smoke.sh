#!/usr/bin/env bash
# Test the PraisonAI installer in Docker
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SMOKE_IMAGE="${PRAISONAI_SMOKE_IMAGE:-praisonai-install-smoke:local}"
INSTALL_URL="${PRAISONAI_INSTALL_URL:-file:///install.sh}"

echo "==> Build smoke test image: $SMOKE_IMAGE"
docker build \
  -t "$SMOKE_IMAGE" \
  -f "$ROOT_DIR/scripts/docker/install-smoke/Dockerfile" \
  "$ROOT_DIR/scripts/docker/install-smoke"

echo "==> Run installer smoke test"
docker run --rm -t \
  -v "$ROOT_DIR/scripts/install.sh:/install.sh:ro" \
  -e PRAISONAI_INSTALL_URL="$INSTALL_URL" \
  -e PRAISONAI_EXPECTED_VERSION="${PRAISONAI_EXPECTED_VERSION:-}" \
  -e PRAISONAI_EXTRAS="${PRAISONAI_EXTRAS:-}" \
  "$SMOKE_IMAGE"

echo "==> Smoke test completed successfully!"
