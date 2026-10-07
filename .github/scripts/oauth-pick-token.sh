#!/usr/bin/env bash
# Pick a working Claude Code OAuth token (primary / secondary / tertiary failover).
# Env: CLAUDE_CODE_OAUTH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN_B, CLAUDE_CODE_OAUTH_TOKEN_C, CLAUDE_OAUTH_ACTIVE
# Out: GITHUB_OUTPUT token, slot
set -euo pipefail

PRIMARY="${CLAUDE_CODE_OAUTH_TOKEN:-}"
SECONDARY="${CLAUDE_CODE_OAUTH_TOKEN_B:-}"
TERTIARY="${CLAUDE_CODE_OAUTH_TOKEN_C:-}"
ACTIVE="${CLAUDE_OAUTH_ACTIVE:-primary}"

ACTIVE_LC=$(echo "$ACTIVE" | tr '[:upper:]' '[:lower:]')
case "$ACTIVE_LC" in
  tertiary|c|3) PREFERRED=tertiary ;;
  secondary|b|2) PREFERRED=secondary ;;
  *) PREFERRED=primary ;;
esac

probe_token() {
  local token=$1
  [[ -z "$token" ]] && return 1

  local body='{"model":"claude-3-5-haiku-latest","max_tokens":1,"messages":[{"role":"user","content":"."}]}'
  local tmp http_code body_resp

  tmp=$(mktemp)
  http_code=$(curl -sS -o "$tmp" -w "%{http_code}" \
    -X POST "https://api.anthropic.com/v1/messages" \
    -H "Authorization: Bearer ${token}" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -d "$body" 2>/dev/null || echo "000")

  body_resp=$(cat "$tmp")
  rm -f "$tmp"

  if [[ "$http_code" == "200" ]] || [[ "$http_code" == "400" ]]; then
    return 0
  fi

  if [[ "$http_code" == "401" ]] || [[ "$http_code" == "429" ]]; then
    echo "::warning::OAuth probe failed (HTTP ${http_code})"
    return 1
  fi

  if echo "$body_resp" | grep -qiE 'revoked|invalid.*token|authentication|weekly limit|rate_limit|overloaded|billing'; then
    echo "::warning::OAuth probe rejected (HTTP ${http_code})"
    return 1
  fi

  return 0
}

try_token() {
  local slot=$1 token=$2
  [[ -z "$token" ]] && return 1
  if probe_token "$token"; then
    SELECTED_SLOT=$slot
    SELECTED_TOKEN=$token
    return 0
  fi
  return 1
}

SELECTED_SLOT=""
SELECTED_TOKEN=""

case "$PREFERRED" in
  tertiary)
    try_token tertiary "$TERTIARY" || try_token secondary "$SECONDARY" || try_token primary "$PRIMARY" || true
    ;;
  secondary)
    try_token secondary "$SECONDARY" || try_token primary "$PRIMARY" || try_token tertiary "$TERTIARY" || true
    ;;
  *)
    try_token primary "$PRIMARY" || try_token secondary "$SECONDARY" || try_token tertiary "$TERTIARY" || true
    ;;
esac

if [[ -z "$SELECTED_TOKEN" ]]; then
  if [[ "$PREFERRED" == "primary" && -n "$PRIMARY" ]]; then
    SELECTED_TOKEN="$PRIMARY"
    SELECTED_SLOT="primary-unprobed"
  elif [[ -n "$SECONDARY" ]]; then
    SELECTED_TOKEN="$SECONDARY"
    SELECTED_SLOT="secondary-unprobed"
  elif [[ -n "$TERTIARY" ]]; then
    SELECTED_TOKEN="$TERTIARY"
    SELECTED_SLOT="tertiary-unprobed"
  elif [[ -n "$PRIMARY" ]]; then
    SELECTED_TOKEN="$PRIMARY"
    SELECTED_SLOT="primary-unprobed"
  else
    echo "::error::No Claude OAuth token configured"
    exit 1
  fi
  echo "::warning::OAuth probe failed for all tokens; using ${SELECTED_SLOT}"
fi

echo "::notice::Claude OAuth slot: ${SELECTED_SLOT}"

if [[ -z "${GITHUB_OUTPUT:-}" ]]; then
  echo "slot=${SELECTED_SLOT}"
  exit 0
fi

{
  echo "token<<EOF"
  echo "$SELECTED_TOKEN"
  echo "EOF"
  echo "slot=${SELECTED_SLOT}"
} >> "$GITHUB_OUTPUT"
