"""
LLM endpoint environment variable resolver.

Provides a single source of truth for resolving LLM endpoint configuration
from environment variables, ensuring consistent precedence across all components.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LLMEndpoint:
    """LLM endpoint configuration resolved from environment variables."""
    model: str
    base_url: str
    api_key: Optional[str]


# Documented, single precedence list. Add new providers here only.
_MODEL_VARS = ("MODEL_NAME", "OPENAI_MODEL_NAME")
_BASE_URL_VARS = ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OLLAMA_API_BASE")
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_BASE = "https://api.openai.com/v1"


def _first_set(*names: str) -> Optional[str]:
    """Return the first environment variable that is set and non-empty."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def resolve_llm_endpoint(*, default_base: str = _DEFAULT_BASE) -> LLMEndpoint:
    """
    Resolve LLM endpoint configuration from environment variables.
    
    Precedence order:
    - Model: MODEL_NAME > OPENAI_MODEL_NAME > default
    - Base URL: OPENAI_BASE_URL > OPENAI_API_BASE > OLLAMA_API_BASE > default
    - API Key: OPENAI_API_KEY
    
    Args:
        default_base: Default base URL if none found in environment variables
        
    Returns:
        LLMEndpoint with resolved configuration
    """
    return LLMEndpoint(
        model=_first_set(*_MODEL_VARS) or _DEFAULT_MODEL,
        base_url=_first_set(*_BASE_URL_VARS) or default_base,
        api_key=os.environ.get("OPENAI_API_KEY"),
    )