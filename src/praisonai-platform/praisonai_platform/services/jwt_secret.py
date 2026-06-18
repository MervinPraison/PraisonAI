"""JWT secret resolution for praisonai-platform (testable, fail-closed in production)."""

from __future__ import annotations

import os
import secrets
import warnings
from typing import Optional

_DEFAULT_SECRET = "dev-secret-change-me"


def resolve_jwt_secret(
    *,
    env: Optional[dict[str, str]] = None,
) -> str:
    """Resolve PLATFORM_JWT_SECRET with production guards."""
    env = env if env is not None else os.environ
    explicit_env = env.get("PLATFORM_ENV")
    raw_secret = env.get("PLATFORM_JWT_SECRET")

    if explicit_env == "production":
        if not raw_secret or raw_secret == _DEFAULT_SECRET:
            raise RuntimeError(
                "PLATFORM_JWT_SECRET must be set to a stable random value when "
                "PLATFORM_ENV=production"
            )
        return raw_secret

    if raw_secret == _DEFAULT_SECRET:
        if explicit_env == "dev":
            return _DEFAULT_SECRET
        raise RuntimeError(
            "PLATFORM_JWT_SECRET cannot be the development default unless "
            "PLATFORM_ENV=dev"
        )

    if raw_secret:
        return raw_secret

    if explicit_env == "dev":
        return _DEFAULT_SECRET

    ephemeral = secrets.token_urlsafe(32)
    warnings.warn(
        "PLATFORM_JWT_SECRET is not set. Auto-generated an ephemeral signing key — "
        "JWT tokens will be invalidated on restart. Set PLATFORM_JWT_SECRET for "
        "production, or PLATFORM_ENV=dev for development defaults.",
        stacklevel=2,
    )
    return ephemeral
