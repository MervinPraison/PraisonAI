"""Claude Code OAuth — read ~/.claude/.credentials.json or macOS Keychain."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .protocols import AuthError, SubscriptionCredentials
from .registry import register_subscription_provider

_CLAUDE_CODE_VERSION_FALLBACK = "2.1.74"


def _detect_claude_code_version() -> str:
    """Detect the installed Claude Code version, fall back to a static constant.
    
    Anthropic's OAuth infrastructure validates the user-agent version and may
    reject requests with a version that's too old. Detecting dynamically means
    users who keep Claude Code updated never hit stale-version 400s.
    """
    cached = getattr(_detect_claude_code_version, "_cache", None)
    if cached:
        return cached
    try:
        out = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=2, check=False
        )
        match = re.match(r"(\d+\.\d+\.\d+)", out.stdout.strip())
        version = match.group(1) if match else _CLAUDE_CODE_VERSION_FALLBACK
    except Exception:
        version = _CLAUDE_CODE_VERSION_FALLBACK
    _detect_claude_code_version._cache = version
    return version


_CLI_USER_AGENT_FALLBACK = f"claude-cli/{_CLAUDE_CODE_VERSION_FALLBACK} (external, cli)"


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
        # Read-only: never refresh here. Anthropic rotates refresh tokens and
        # PraisonAI does not write back to Keychain, which would invalidate
        # Claude CLI and other tools sharing the same session.
        return SubscriptionCredentials(
            api_key=creds["accessToken"],
            base_url="https://api.anthropic.com",
            headers=self.headers_for("https://api.anthropic.com", ""),
            auth_scheme="bearer",
            expires_at_ms=creds.get("expiresAt"),
            source=creds["source"],
        )

    def refresh(self) -> SubscriptionCredentials:
        raise AuthError(
            "PraisonAI does not refresh shared Claude Code OAuth sessions "
            "(refresh-token rotation would invalidate Claude CLI and other "
            "tools using the same Keychain entry). Run 'claude /login' or "
            "let Claude CLI refresh credentials, then retry."
        )

    def headers_for(self, base_url: str, model: str) -> Dict[str, str]:
        # CRITICAL: without these headers Anthropic returns 500s on OAuth tokens.
        # Match Hermes' OAuth header set exactly. litellm auto-adds oauth-2025-04-20.
        return {
            "anthropic-beta": ",".join([
                "interleaved-thinking-2025-05-14",
                "fine-grained-tool-streaming-2025-05-14",
                "claude-code-20250219",
            ]),
            "user-agent":     f"claude-cli/{_detect_claude_code_version()} (external, cli)",
            "x-app":          "cli",
        }


register_subscription_provider("claude-code", lambda: ClaudeCodeAuth())