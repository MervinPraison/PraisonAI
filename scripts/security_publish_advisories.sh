#!/usr/bin/env bash
# Publish security advisories after PyPI release.
# Usage: AGENTS_VERSION=1.6.40 WRAPPER_VERSION=4.6.40 ./scripts/security_publish_advisories.sh
set -euo pipefail

REPO="MervinPraison/PraisonAI"
AGENTS_VERSION="${AGENTS_VERSION:?Set AGENTS_VERSION (e.g. 1.6.40)}"
WRAPPER_VERSION="${WRAPPER_VERSION:?Set WRAPPER_VERSION (e.g. 4.6.40)}"
LAST_AGENTS="${LAST_AGENTS:-1.6.39}"
LAST_WRAPPER="${LAST_WRAPPER:-4.6.39}"

# Batch 1 + 2 GHSA IDs (update credits login per advisory via gh api first if needed)
AGENTS_GHSAS=(
  GHSA-4mr5-g6f9-cfrh
  GHSA-5c6w-wwfq-7qqm
  GHSA-5cxw-77wg-jrf3
)

WRAPPER_GHSAS=(
  GHSA-9cr9-25q5-8prj
  GHSA-86qc-r5v2-v6x6
  GHSA-hvhp-v2gc-268q
  GHSA-xp85-6wwf-r67c
  GHSA-8444-4fhq-fxpq
  GHSA-78r8-wwqv-r299
  GHSA-vg22-4gmj-prxw
  GHSA-6xj3-927j-6pqw
)

patch_advisory() {
  local ghsa="$1" package="$2" last="$3" patched="$4"
  gh api "repos/${REPO}/security-advisories/${ghsa}" --method PATCH --input - <<EOF
{
  "state": "draft",
  "vulnerabilities": [
    {
      "package": {"ecosystem": "pip", "name": "${package}"},
      "vulnerable_version_range": "<= ${last}",
      "patched_versions": ">= ${patched}"
    }
  ]
}
EOF
  gh api "repos/${REPO}/security-advisories/${ghsa}" --method PATCH -f state=published
  gh api "repos/${REPO}/security-advisories/${ghsa}/cve" --method POST || true
  echo "Published ${ghsa}"
}

for ghsa in "${AGENTS_GHSAS[@]}"; do
  patch_advisory "$ghsa" "praisonaiagents" "$LAST_AGENTS" "$AGENTS_VERSION"
done

for ghsa in "${WRAPPER_GHSAS[@]}"; do
  patch_advisory "$ghsa" "praisonai" "$LAST_WRAPPER" "$WRAPPER_VERSION"
done

echo "Done. Verify: gh api repos/${REPO}/security-advisories --jq '.[] | select(.state==\"published\") | .ghsa_id'"
