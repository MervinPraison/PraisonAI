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


# Map well-known model prefixes to their (env-var, default base_url).
_PROVIDER_MAP = {
    "anthropic/":  ("ANTHROPIC_API_KEY",  None),
    "google/":     ("GOOGLE_API_KEY",     None),
    "gemini/":     ("GEMINI_API_KEY",     None),
    "groq/":       ("GROQ_API_KEY",       "https://api.groq.com/openai/v1"),
    "cohere/":     ("COHERE_API_KEY",     None),
    "openrouter/": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    "ollama/":     ("OLLAMA_API_KEY",     "http://localhost:11434/v1"),
}

# Documented, single precedence list. Add new providers here only.
_MODEL_VARS = ("MODEL_NAME", "OPENAI_MODEL_NAME")
_BASE_URL_VARS = ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OLLAMA_API_BASE")
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_BASE = "https://api.openai.com/v1"
_DEFAULT_KEY_VAR = "OPENAI_API_KEY"


def _first_set(*names: str) -> Optional[str]:
    """Return the first environment variable that is set and non-empty."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _provider_from_model(model: str) -> tuple[str, str | None]:
    """Get provider-specific API key environment variable and base URL for a model."""
    for prefix, (key_var, default_base) in _PROVIDER_MAP.items():
        if model.startswith(prefix):
            return key_var, default_base
    return _DEFAULT_KEY_VAR, None


def resolve_llm_endpoint(*, default_base: str = _DEFAULT_BASE) -> LLMEndpoint:
    """
    Resolve LLM endpoint configuration from environment variables.
    
    Precedence order:
    - Model: MODEL_NAME > OPENAI_MODEL_NAME > default
    - Base URL: OPENAI_BASE_URL > OPENAI_API_BASE > OLLAMA_API_BASE > provider default > default
    - API Key: provider-specific key (e.g., ANTHROPIC_API_KEY) > OPENAI_API_KEY fallback
    
    Args:
        default_base: Default base URL if none found in environment variables
        
    Returns:
        LLMEndpoint with resolved configuration
    """
    model = _first_set(*_MODEL_VARS) or _DEFAULT_MODEL
    key_var, provider_base = _provider_from_model(model)

    base_url = (
        _first_set(*_BASE_URL_VARS)
        or provider_base
        or default_base
    )
    
    # api_key is read from the provider-specific var, falling back to OPENAI_API_KEY
    # only when the model is the default OpenAI shape.
    api_key = os.environ.get(key_var) or (
        os.environ.get("OPENAI_API_KEY") if key_var != "OPENAI_API_KEY" else None
    )
    
    return LLMEndpoint(model=model, base_url=base_url, api_key=api_key)