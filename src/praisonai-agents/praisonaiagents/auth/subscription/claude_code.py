"""Claude Code OAuth — read ~/.claude/.credentials.json or macOS Keychain."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from .protocols import AuthError, SubscriptionAuthProtocol, SubscriptionCredentials
from .registry import register_subscription_provider

_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_TOKEN_ENDPOINTS = (
    "https://platform.claude.com/v1/oauth/token",
    "https://console.anthropic.com/v1/oauth/token",
)
_CLI_USER_AGENT_FALLBACK = "claude-cli/2.1.0 (external, cli)"


def _read_keychain_credentials() -> Optional[Dict[str, Any]]:
    """Read 'Claude Code-credentials' entry from macOS Keychain.

    Returns dict with accessToken/refreshToken/expiresAt or None.
    """
    if sys.platform != "darwin":
        return None
    import subprocess
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        data = json.loads(out.stdout)
        oauth = data.get("claudeAiOauth") or {}
        if oauth.get("accessToken"):
            return {
                "accessToken":  oauth["accessToken"],
                "refreshToken": oauth.get("refreshToken", ""),
                "expiresAt":    int(oauth.get("expiresAt", 0)),
                "source":       "claude-code-keychain",
            }
    except Exception:
        return None
    return None


def _read_file_credentials() -> Optional[Dict[str, Any]]:
    """Read ~/.claude/.credentials.json."""
    path = Path.home() / ".claude" / ".credentials.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    oauth = data.get("claudeAiOauth") or {}
    if not oauth.get("accessToken"):
        return None
    return {
        "accessToken":  oauth["accessToken"],
        "refreshToken": oauth.get("refreshToken", ""),
        "expiresAt":    int(oauth.get("expiresAt", 0)),
        "source":       "claude-code-file",
    }


def _is_expiring(expires_at_ms: Optional[int], skew_ms: int = 60_000) -> bool:
    if not expires_at_ms:
        return False
    return int(time.time() * 1000) >= (expires_at_ms - skew_ms)


def _refresh(refresh_token: str) -> Dict[str, Any]:
    """Pure refresh — does not touch local files."""
    if not refresh_token:
        raise AuthError("no refresh_token; please re-run 'claude /login'")
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": _OAUTH_CLIENT_ID,
    }).encode()
    last = None
    for endpoint in _TOKEN_ENDPOINTS:
        req = urllib.request.Request(
            endpoint, data=body, method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent":   _CLI_USER_AGENT_FALLBACK,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode())
            return {
                "accessToken":  payload["access_token"],
                "refreshToken": payload.get("refresh_token", refresh_token),
                "expiresAt":    int(time.time() * 1000) + int(payload.get("expires_in", 3600)) * 1000,
            }
        except Exception as exc:
            last = exc
    raise AuthError(f"Anthropic refresh failed: {last}")


class ClaudeCodeAuth:
    """Claude Code OAuth subscription auth."""

    name = "claude-code"

    def resolve_credentials(self) -> SubscriptionCredentials:
        # 1. ANTHROPIC_TOKEN / CLAUDE_CODE_OAUTH_TOKEN env (Hermes-style)
        for env_key in ("ANTHROPIC_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
            tok = os.environ.get(env_key, "").strip()
            if tok:
                return SubscriptionCredentials(
                    api_key=tok,
                    base_url="https://api.anthropic.com",
                    headers=self.headers_for("https://api.anthropic.com", ""),
                    auth_scheme="bearer",
                    source=f"env:{env_key}",
                )

        # 2. Keychain or file
        creds = _read_keychain_credentials() or _read_file_credentials()
        if not creds:
            raise AuthError(
                "No Claude Code credentials found. Install Claude Code and run "
                "'claude /login', or set ANTHROPIC_TOKEN."
            )
        if _is_expiring(creds["expiresAt"]) and creds.get("refreshToken"):
            creds.update(_refresh(creds["refreshToken"]))
        return SubscriptionCredentials(
            api_key=creds["accessToken"],
            base_url="https://api.anthropic.com",
            headers=self.headers_for("https://api.anthropic.com", ""),
            auth_scheme="bearer",
            expires_at_ms=creds.get("expiresAt"),
            source=creds["source"],
        )

    def refresh(self) -> SubscriptionCredentials:
        creds = _read_keychain_credentials() or _read_file_credentials()
        if not creds or not creds.get("refreshToken"):
            raise AuthError("cannot refresh: no refresh token available")
        new = _refresh(creds["refreshToken"])
        return SubscriptionCredentials(
            api_key=new["accessToken"],
            base_url="https://api.anthropic.com",
            headers=self.headers_for("https://api.anthropic.com", ""),
            auth_scheme="bearer",
            expires_at_ms=new["expiresAt"],
            source="claude-code-refreshed",
        )

    def headers_for(self, base_url: str, model: str) -> Dict[str, str]:
        # CRITICAL: without these headers Anthropic returns 500s on OAuth tokens.
        # Mirrors hermes-agent/agent/anthropic_adapter.py:578-588.
        return {
            "anthropic-beta": "oauth-2025-04-20,interleaved-thinking-2025-05-14",
            "user-agent":     _CLI_USER_AGENT_FALLBACK,
            "x-app":          "cli",
        }


register_subscription_provider("claude-code", lambda: ClaudeCodeAuth())