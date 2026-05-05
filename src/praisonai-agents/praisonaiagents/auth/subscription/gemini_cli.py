"""Gemini CLI OAuth — read ~/.gemini/oauth_creds.json."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .protocols import AuthError, SubscriptionCredentials
from .registry import register_subscription_provider


_GEMINI_BASE_URL = "https://cloudcode-pa.googleapis.com/v1internal"


def _read_gemini_tokens() -> Optional[Dict[str, Any]]:
    """Read Gemini CLI OAuth credentials."""
    auth_path = Path.home() / ".gemini" / "oauth_creds.json"
    if not auth_path.is_file():
        return None
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not payload.get("access_token"):
        return None
    return payload


class GeminiCliAuth:
    name = "gemini-cli"

    def resolve_credentials(self) -> SubscriptionCredentials:
        tokens = _read_gemini_tokens()
        if not tokens:
            raise AuthError(
                "No Gemini CLI credentials at ~/.gemini/oauth_creds.json. "
                "Install Gemini CLI and run 'gemini auth'."
            )
        return SubscriptionCredentials(
            api_key=tokens["access_token"],
            base_url=os.environ.get("PRAISONAI_GEMINI_BASE_URL", "").strip() or _GEMINI_BASE_URL,
            headers=self.headers_for(_GEMINI_BASE_URL, ""),
            auth_scheme="bearer",
            source="gemini-cli-file",
        )

    def refresh(self) -> SubscriptionCredentials:
        # Gemini CLI handles refresh internally
        return self.resolve_credentials()

    def headers_for(self, base_url: str, model: str) -> Dict[str, str]:
        return {
            "user-agent": "gemini-cli/1.0.0 (external)",
        }


register_subscription_provider("gemini-cli", lambda: GeminiCliAuth())