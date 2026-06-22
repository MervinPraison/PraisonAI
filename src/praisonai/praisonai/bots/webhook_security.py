"""Shared webhook verification helpers for bot integrations."""

from __future__ import annotations

import os


def webhooks_require_verification() -> bool:
    """Return True unless explicit dev override disables signature checks."""
    return os.environ.get("PRAISONAI_INSECURE_WEBHOOKS", "").lower() not in (
        "true",
        "1",
        "yes",
    )
