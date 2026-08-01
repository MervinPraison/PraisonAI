#!/usr/bin/env bash
# Lint and template-render all Helm charts under package infra/ trees.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v helm >/dev/null 2>&1; then
  echo "FAIL: helm CLI not found (install via https://helm.sh/docs/intro/install/)"
  exit 1
fi

HELM_ROOTS=(
  "$ROOT/src/praisonai-bot/infra/helm"
  "$ROOT/src/praisonai-deploy/infra/helm"
)

charts=()
for helm_root in "${HELM_ROOTS[@]}"; do
  if [ ! -d "$helm_root" ]; then
    continue
  fi
  shopt -s nullglob
  for chart in "$helm_root"/*/; do
    if [ -f "${chart}Chart.yaml" ]; then
      charts+=("$chart")
    fi
  done
  shopt -u nullglob
done

if [ ${#charts[@]} -eq 0 ]; then
  echo "No charts found under package infra/helm trees"
  exit 1
fi

for chart in "${charts[@]}"; do
  name="$(basename "$chart")"
  echo "== helm lint: $name =="
  helm lint "$chart"

  echo "== helm template: $name =="
  case "$name" in
    praisonai-gateway)
      helm template "ci-smoke-$name" "$chart" \
        --set auth.existingSecret=ci-smoke-auth \
        >/dev/null
      ;;
    praisonai-agents-api)
      helm template "ci-smoke-$name" "$chart" \
        --set auth.existingSecret=ci-smoke-auth \
        --set postgres.auth.existingSecret=ci-smoke-postgres \
        >/dev/null
      ;;
    *)
      helm template "ci-smoke-$name" "$chart" >/dev/null
      ;;
  esac
done

echo "Helm chart gates passed (${#charts[@]} chart(s))"
