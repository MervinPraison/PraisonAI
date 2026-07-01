"""Shared AutoGen-style ``config_list`` builder."""

from __future__ import annotations

from typing import Any


def build_config_list(*, include_api_type: bool = True) -> list[dict[str, Any]]:
    """Build an AutoGen-style ``config_list`` from the resolved endpoint.

    Uses the credential-store aware resolver so a stored credential's own
    ``model``/``base_url`` (e.g. a saved OpenRouter endpoint) is honoured
    after ``inject_credentials_into_env`` exports only the API key. Falls
    back to the env-only resolver if the credential bridge is unavailable.
    Environment variables still take precedence inside the resolver.
    """
    try:
        from praisonai_code.llm.credentials import (
            resolve_llm_endpoint_with_credentials,
        )

        ep = resolve_llm_endpoint_with_credentials()
    except Exception:
        from praisonai_code.llm.env import resolve_llm_endpoint

        ep = resolve_llm_endpoint()

    entry: dict[str, Any] = {
        "model": ep.model,
        "base_url": ep.base_url,
        "api_key": ep.api_key,
    }
    if include_api_type:
        entry["api_type"] = "openai"
    return [entry]
