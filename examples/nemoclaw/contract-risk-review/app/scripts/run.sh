#!/usr/bin/env bash
# Runs inside the OpenShell sandbox:
#   openshell sandbox create --from <image> --policy policy.yaml -- bash /app/scripts/run.sh
#
# 1. Normalise the proxy / CA environment so inference.local goes through the
#    OpenShell proxy (it has no DNS record inside the sandbox).
# 2. Run the deterministic probe, then the 3-agent PraisonAI team.
# 3. Print every artifact between ===BEGIN/END <file>=== markers so the host-side
#    scripts/verify.sh can check them from the captured log.
set -euo pipefail

WORK=/sandbox/work

# --- Proxy / CA normalisation (same idea as NemoClaw's Deep Agents start.sh) ---
_proxy="${HTTPS_PROXY:-${https_proxy:-http://10.200.0.1:3128}}"
_proxy_host="${_proxy#*://}"
_proxy_host="${_proxy_host%%:*}"
export HTTP_PROXY="$_proxy" HTTPS_PROXY="$_proxy" http_proxy="$_proxy" https_proxy="$_proxy"
# inference.local must NOT be in NO_PROXY: it only resolves through the proxy.
export NO_PROXY="localhost,127.0.0.1,::1,${_proxy_host}" no_proxy="localhost,127.0.0.1,::1,${_proxy_host}"
unset ALL_PROXY all_proxy OPENAI_PROXY
if [ -f /etc/openshell-tls/ca-bundle.pem ]; then
  export SSL_CERT_FILE=/etc/openshell-tls/ca-bundle.pem REQUESTS_CA_BUNDLE=/etc/openshell-tls/ca-bundle.pem
fi

dump_artifacts() {
  local rc=$?
  sha256sum /etc/hosts | cut -d' ' -f1 > "$WORK/hosts.sha256.after" 2>/dev/null || true
  for f in probe.json metrics.json risk_report.md audit.jsonl hosts.sha256.before hosts.sha256.after; do
    if [ -f "$WORK/$f" ]; then
      printf '\n===BEGIN %s===\n' "$f"
      cat "$WORK/$f"
      printf '\n===END %s===\n' "$f"
    fi
  done
  printf '\n===EXIT %s===\n' "$rc"
}

rm -rf "$WORK" && cp -r /app "$WORK" && cd "$WORK"
trap dump_artifacts EXIT
sha256sum /etc/hosts | cut -d' ' -f1 > hosts.sha256.before

python probes/sandbox_probe.py > probe.json
praisonai agents.yaml --trust --metrics --metrics-json metrics.json
test -s risk_report.md
