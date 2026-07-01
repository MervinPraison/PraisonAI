"""
LLM endpoint environment variable resolver.

Provides a single source of truth for resolving LLM endpoint configuration
from environment variables, ensuring consistent precedence across all components.
"""

import os
from dataclasses import dataclass
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonai_code.cli.configuration.resolver import ResolvedConfig


@dataclass(frozen=True)
class LLMEndpoint:
    """LLM endpoint configuration resolved from environment variables."""
    model: str
    base_url: str
    api_key: Optional[str]


# Map well-known model prefixes to their (env-var, default base_url).
_PROVIDER_MAP = {
    "anthropic/":  ("ANTHROPIC_API_KEY",  "https://api.anthropic.com/v1"),
    "google/":     ("GOOGLE_API_KEY",     "https://generativelanguage.googleapis.com/v1beta"),
    "gemini/":     ("GEMINI_API_KEY",     "https://generativelanguage.googleapis.com/v1beta"),
    "groq/":       ("GROQ_API_KEY",       "https://api.groq.com/openai/v1"),
    "cohere/":     ("COHERE_API_KEY",     "https://api.cohere.ai/v1"),
    "openrouter/": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    "ollama/":     ("OLLAMA_API_KEY",     "http://localhost:11434/v1"),
}

# Documented, single precedence list. Add new providers here only.
_MODEL_VARS = ("MODEL_NAME", "OPENAI_MODEL_NAME")
_BASE_URL_VARS = ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OLLAMA_API_BASE")
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_BASE = "https://api.openai.com/v1"
_DEFAULT_KEY_VAR = "OPENAI_API_KEY"

# Ordered list of (credential env-var, provider-appropriate default model).
_PROVIDER_DEFAULTS = (
    ("OPENAI_API_KEY", "gpt-4o-mini"),
    ("ANTHROPIC_API_KEY", "anthropic/claude-3-5-sonnet-latest"),
    ("GEMINI_API_KEY", "gemini/gemini-1.5-flash"),
    ("GOOGLE_API_KEY", "google/gemini-1.5-flash"),
    ("GROQ_API_KEY", "groq/llama-3.3-70b-versatile"),
    ("COHERE_API_KEY", "cohere/command-r"),
    ("OLLAMA_HOST", "ollama/llama3.2"),
)


def _load_model_catalogue():
    """Optional model catalogue (wrapper); skipped when standalone."""
    try:
        from praisonai_code._wrapper_bridge import optional_wrapper_attr

        catalogue_cls = optional_wrapper_attr("praisonai.llm.catalogue", "ModelCatalogue")
        return catalogue_cls() if catalogue_cls is not None else None
    except Exception:
        return None


def default_model_for_available_provider(
    *, validate: bool = False
) -> str:
    """
    Choose a default model that matches an available provider credential.

    Inspects the same credential environment variables that ``is_configured``
    knows about and returns a provider-appropriate default model. When no
    supported provider credential is present, falls back to ``_DEFAULT_MODEL``.
    """
    catalogue = _load_model_catalogue() if validate else None

    for key_var, model in _PROVIDER_DEFAULTS:
        if not os.environ.get(key_var):
            continue
        if catalogue is not None:
            bare = model.split("/", 1)[-1]
            try:
                catalogue.validate_model(bare)
            except Exception:
                pass
        return model

    return _DEFAULT_MODEL


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


def resolve_llm_endpoint(
    *,
    default_base: str = _DEFAULT_BASE,
    fallback_lookup: Optional[Callable[[str], Optional[dict]]] = None,
    resolved_config: Optional["ResolvedConfig"] = None,
    validate_model: bool = False
) -> LLMEndpoint:
    """Resolve LLM endpoint configuration from environment variables and config."""
    env_model = _first_set(*_MODEL_VARS)

    if env_model:
        model = env_model
    elif resolved_config and resolved_config.agent.model:
        model = resolved_config.agent.model
    else:
        model = default_model_for_available_provider(validate=validate_model)

    catalogue = _load_model_catalogue() if validate_model else None
    if validate_model and catalogue is not None:
        try:
            model = catalogue.validate_model(model)
        except ValueError:
            raise

    key_var, provider_base = _provider_from_model(model)

    env_base = _first_set(*_BASE_URL_VARS)
    if env_base:
        base_url = env_base
    elif resolved_config and resolved_config.agent.base_url:
        base_url = resolved_config.agent.base_url
    else:
        base_url = provider_base or default_base

    api_key = os.environ.get(key_var) or (
        os.environ.get("OPENAI_API_KEY") if key_var == "OPENAI_API_KEY" else None
    )

    fallback_model = None
    fallback_base = None
    if not api_key and fallback_lookup:
        try:
            for provider in ["openai", "anthropic", "google", "gemini", "groq", "cohere"]:
                cred = fallback_lookup(provider)
                if cred and cred.get("api_key"):
                    api_key = cred["api_key"]
                    fallback_model = cred.get("model")
                    fallback_base = cred.get("base_url")
                    if validate_model and fallback_model and catalogue:
                        try:
                            fallback_model = catalogue.validate_model(fallback_model)
                        except ValueError:
                            api_key = None
                            fallback_model = None
                            fallback_base = None
                            continue
                    break
        except Exception:
            pass

    return LLMEndpoint(
        model=fallback_model or model,
        base_url=fallback_base or base_url,
        api_key=api_key,
    )
