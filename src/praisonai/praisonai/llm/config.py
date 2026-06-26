"""Shared AutoGen-style ``config_list`` builder.

Provides a single owner for turning a resolved LLM endpoint into the
``[{model, base_url, api_key, api_type}]`` shape that AutoGen and the
PraisonAI wrappers expect. Keeps endpoint->config mapping in one place so
new fields or provider quirks only need to change here.
"""
from __future__ import annotations

from typing import Any


def build_config_list(*, include_api_type: bool = True) -> list[dict[str, Any]]:
    """Build an AutoGen-style ``config_list`` from the resolved endpoint.

    Reuses the same env/keyfile resolution the CLI already performs via
    :func:`praisonai.llm.env.resolve_llm_endpoint`.

    Args:
        include_api_type: When True, include ``api_type='openai'`` which
            AutoGen expects. Set False to match callers that historically
            omit it.

    Returns:
        A single-entry list with the resolved model, base URL and API key.
    """
    from praisonai.llm.env import resolve_llm_endpoint
    ep = resolve_llm_endpoint()

    entry: dict[str, Any] = {
        'model': ep.model,
        'base_url': ep.base_url,
        'api_key': ep.api_key,
    }
    if include_api_type:
        entry['api_type'] = 'openai'        # AutoGen expects this field
    return [entry]
