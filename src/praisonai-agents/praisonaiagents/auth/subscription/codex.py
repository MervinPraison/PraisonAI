"""Codex / ChatGPT subscription — read ~/.codex/auth.json (or CODEX_HOME)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .protocols import AuthError, SubscriptionCredentials
from .registry import register_subscription_provider


_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"


def _read_codex_tokens() -> Optional[Dict[str, Any]]:
    home = os.environ.get("CODEX_HOME", "").strip() or str(Path.home() / ".codex")
    auth_path = Path(home).expanduser() / "auth.json"
    if not auth_path.is_file():
        return None
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    tokens = payload.get("tokens") or {}
    if not tokens.get("access_token") or not tokens.get("refresh_token"):
        return None
    return tokens


def _is_jwt_expiring(jwt: str, skew_seconds: int = 60) -> bool:
    """Decode JWT exp claim without verifying signature."""
    import base64
    try:
        _hdr, payload_b64, _sig = jwt.split(".")
        pad = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + pad))
        exp = int(payload.get("exp", 0))
        return exp and (time.time() + skew_seconds) >= exp
    except Exception:
        return False  # treat unknown as not-expiring; refresh on actual 401


class CodexAuth:
    name = "codex"

    def resolve_credentials(self) -> SubscriptionCredentials:
        # EXPERIMENTAL: Codex uses Responses API, not Chat Completions
        # OpenAI chat-completions requests will 404 against this endpoint
        raise AuthError(
            "Codex auth is experimental and requires custom Responses API transport. "
            "Use a standard OpenAI API key or wait for proper Codex support in a future release."
        )

    def refresh(self) -> SubscriptionCredentials:
        # OpenAI Codex tokens are refreshed by the Codex CLI itself; we rely
        # on the CLI being run periodically. A direct refresh would require
        # replicating their device-flow client — out of scope for v1.
        return self.resolve_credentials()

    def headers_for(self, base_url: str, model: str) -> Dict[str, str]:
        return {
            "openai-beta": "responses=v1",
            "user-agent":  "codex-cli/0.1.0 (external)",
        }


register_subscription_provider("codex", lambda: CodexAuth())