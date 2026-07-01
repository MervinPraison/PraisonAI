"""Shared AutoGen-style ``config_list`` builder."""

from __future__ import annotations

from typing import Any


def build_config_list(*, include_api_type: bool = True) -> list[dict[str, Any]]:
    """Build an AutoGen-style ``config_list`` from the resolved endpoint."""
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
