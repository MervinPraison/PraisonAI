"""Qwen CLI OAuth — read ~/.qwen/oauth_creds.json."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .protocols import AuthError, SubscriptionCredentials
from .registry import register_subscription_provider


_QWEN_BASE_URL = "https://portal.qwen.ai/v1"


def _read_qwen_tokens() -> Optional[Dict[str, Any]]:
    """Read Qwen CLI OAuth credentials."""
    auth_path = Path.home() / ".qwen" / "oauth_creds.json"
    if not auth_path.is_file():
        return None
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not payload.get("access_token"):
        return None
    return payload


class QwenCliAuth:
    name = "qwen-cli"

    def resolve_credentials(self) -> SubscriptionCredentials:
        tokens = _read_qwen_tokens()
        if not tokens:
            raise AuthError(
                "No Qwen CLI credentials at ~/.qwen/oauth_creds.json. "
                "Install Qwen CLI and run 'qwen login'."
            )
        return SubscriptionCredentials(
            api_key=tokens["access_token"],
            base_url=os.environ.get("PRAISONAI_QWEN_BASE_URL", "").strip() or _QWEN_BASE_URL,
            headers=self.headers_for(_QWEN_BASE_URL, ""),
            auth_scheme="bearer",
            source="qwen-cli-file",
        )

    def refresh(self) -> SubscriptionCredentials:
        # Qwen CLI handles refresh internally
        return self.resolve_credentials()

    def headers_for(self, base_url: str, model: str) -> Dict[str, str]:
        return {
            "user-agent": "qwen-cli/1.0.0 (external)",
        }


register_subscription_provider("qwen-cli", lambda: QwenCliAuth())