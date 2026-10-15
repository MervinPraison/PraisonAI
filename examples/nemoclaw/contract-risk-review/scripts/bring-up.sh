#!/usr/bin/env bash
# Host side: create the provider + route, build the image, run the team in an
# OpenShell sandbox and capture the log to out/run.log for verify.sh.
# Requires: docker, openshell (pinned, see README), NVIDIA_API_KEY.
# Use a DEDICATED gateway: `openshell inference set` changes the route for every
# sandbox on the gateway.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="${NAME:-praisonai-demo}"
IMAGE="${IMAGE:-praisonai-contract-review:dev}"
MODEL="${MODEL:-nvidia/nemotron-3-super-120b-a12b}"
OPENSHELL_VERSION="${OPENSHELL_VERSION:-0.0.116}"

: "${NVIDIA_API_KEY:?Set NVIDIA_API_KEY}"
if ! openshell --version 2>/dev/null | grep -q "$OPENSHELL_VERSION"; then
  echo "warning: expected OpenShell $OPENSHELL_VERSION, got: $(openshell --version 2>&1 || echo none)" >&2
  echo "         OpenShell 0.1.0 removed 'openshell inference' and inference.local." >&2
fi

openshell provider create --name "$NAME" --type nvidia --credential NVIDIA_API_KEY
openshell inference set --provider "$NAME" --model "$MODEL"
docker build -t "$IMAGE" "$HERE"

mkdir -p "$HERE/out"
# Capture the full run; run.sh prints every artifact between ===BEGIN/END=== markers.
set +e
openshell sandbox create --from "$IMAGE" --name "$NAME" --policy "$HERE/policy.yaml" \
  -- bash /app/scripts/run.sh 2>&1 | tee "$HERE/out/run.log"
rc=${PIPESTATUS[0]}
set -e
echo "sandbox run exited with $rc; now run scripts/verify.sh"
exit "$rc"
