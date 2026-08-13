"""
LLM credential resolution bridge.

Bridges the credential store with LLM endpoint resolution to provide
seamless credential fallback when environment variables are not set.
"""

from typing import Optional, Dict, Any

from praisonai_code.cli.configuration.credentials import CredentialStore
from praisonai_code.llm.env import (
    resolve_llm_endpoint,
    LLMEndpoint,
    default_model_for_available_provider,
)


def _credential_lookup(provider: str) -> Optional[Dict[str, Any]]:
    """Lookup stored credentials for LLM endpoint fallback."""
    try:
        store = CredentialStore()
        credential = store.get_credential(provider)
        if credential:
            data: Dict[str, Any] = {
                "provider": credential.provider,
                "api_key": credential.api_key,
                "base_url": credential.base_url,
                "model": credential.model,
                "metadata": credential.metadata,
            }
            if credential.is_oauth():
                data["api_key"] = store.get_valid_token(provider)
            return data
    except Exception:
        pass
    return None


def resolve_llm_endpoint_with_credentials(
    *,
    default_base: str = "https://api.openai.com/v1",
    validate_model: bool = False
) -> LLMEndpoint:
    """Resolve LLM configuration with credential store fallback."""
    return resolve_llm_endpoint(
        default_base=default_base,
        fallback_lookup=_credential_lookup,
        validate_model=validate_model
    )


def inject_credentials_into_env() -> bool:
    """Export stored credentials into process environment variables."""
    import os

    try:
        store = CredentialStore()
        providers = store.list_providers()
        injected = False

        env_mappings = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "tavily": "TAVILY_API_KEY",
            "groq": "GROQ_API_KEY",
            "cohere": "COHERE_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }

        for provider in providers:
            env_var = env_mappings.get(provider.lower())
            if not env_var:
                continue
            if os.environ.get(env_var):
                continue

            credential = store.get_credential(provider)
            if not credential:
                continue

            if credential.is_oauth():
                token = store.get_valid_token(provider)
            else:
                token = credential.api_key
            if token:
                os.environ[env_var] = token
                injected = True
                if provider.lower() == "openai" and credential.base_url:
                    if not os.environ.get("OPENAI_BASE_URL"):
                        os.environ["OPENAI_BASE_URL"] = credential.base_url

        return injected

    except Exception:
        return False


def detect_local_endpoint():
    """Return a detected local OpenAI-compatible endpoint, or ``None``.

    Thin bridge over :func:`praisonai_code.llm.local_detect.detect_local_model`
    so the CLI gates (`app.py`, `run.py`) can offer a keyless local-first path
    without importing the detector directly. Never raises.
    """
    try:
        from praisonai_code.llm.local_detect import detect_local_model
        return detect_local_model()
    except Exception:
        return None


def _provider_key_vars_for_model(model: str) -> tuple[str, ...]:
    """Map a model id to the environment variable(s) for its provider.

    Catalogue-driven: consults ``PROVIDER_ENV_CATALOGUE`` so any provider it
    declares (Mistral, DeepSeek, xAI, …) resolves, not a hardcoded head.
    """
    if not model:
        return ()
    try:
        from praisonai_code.llm.catalogue import (
            provider_for_model,
            env_vars_for_provider,
        )

        provider = provider_for_model(model)
        if provider:
            vars_ = env_vars_for_provider(provider)
            if vars_:
                return vars_
    except Exception:
        pass

    m = model.lower()
    if m.startswith("anthropic/") or m.startswith("claude"):
        return ("ANTHROPIC_API_KEY",)
    if m.startswith("google/"):
        return ("GOOGLE_API_KEY",)
    if m.startswith("gemini/") or m.startswith("gemini"):
        return ("GEMINI_API_KEY",)
    if m.startswith("groq/"):
        return ("GROQ_API_KEY",)
    if m.startswith("cohere/"):
        return ("COHERE_API_KEY",)
    if m.startswith("openrouter/"):
        return ("OPENROUTER_API_KEY",)
    if m.startswith("ollama/"):
        return ("OLLAMA_HOST",)
    if (
        m.startswith("gpt")
        or m.startswith("o1")
        or m.startswith("o3")
        or m.startswith("o4")
        or m.startswith("openai/")
    ):
        return ("OPENAI_API_KEY",)
    return ()


_VAR_TO_STORED_PROVIDERS = {
    "OPENAI_API_KEY": ("openai",),
    "ANTHROPIC_API_KEY": ("anthropic",),
    "GEMINI_API_KEY": ("gemini", "google"),
    "GOOGLE_API_KEY": ("google", "gemini"),
    "GROQ_API_KEY": ("groq",),
    "COHERE_API_KEY": ("cohere",),
    "OPENROUTER_API_KEY": ("openrouter",),
    "OLLAMA_HOST": ("ollama",),
}


def _known_credential_vars() -> tuple[str, ...]:
    """Return every credential env-var the first-run gate should honour.

    Catalogue-driven so a valid key for any catalogued provider (Mistral,
    DeepSeek, Together, Fireworks, xAI, Perplexity, …) counts as configured.
    Falls back to the historical 8-key set if the catalogue is unavailable.
    """
    try:
        from praisonai_code.llm.catalogue import provider_env_vars

        vars_ = provider_env_vars()
        if vars_:
            return vars_
    except Exception:
        pass
    return (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
        "GEMINI_API_KEY", "GROQ_API_KEY", "COHERE_API_KEY",
        "OPENROUTER_API_KEY", "OLLAMA_HOST",
    )


def _stored_providers_for_vars(vars_: tuple[str, ...]) -> tuple[str, ...]:
    """Return stored-credential provider names matching the given env-vars.

    Catalogue-driven: any catalogued provider (Mistral, DeepSeek, xAI,
    Together, Perplexity, Fireworks, …) whose credential env-var appears in
    ``vars_`` is recognised, so a stored key for an explicit provider-prefixed
    model satisfies ``is_configured()``. The historical
    ``_VAR_TO_STORED_PROVIDERS`` aliases (e.g. GOOGLE/GEMINI) are layered on top
    to preserve the prior cross-mapping behaviour.
    """
    out: list[str] = []

    try:
        from praisonai_code.llm.catalogue import PROVIDER_ENV_CATALOGUE

        for provider, (env_vars, _model, _prefix) in PROVIDER_ENV_CATALOGUE.items():
            if any(v in vars_ for v in env_vars):
                if provider not in out:
                    out.append(provider)
    except Exception:
        pass

    for v in vars_:
        for provider in _VAR_TO_STORED_PROVIDERS.get(v, ()):
            if provider not in out:
                out.append(provider)

    return tuple(out)


def is_configured(model: Optional[str] = None) -> bool:
    """Check if credentials are configured for the specified or default model."""
    import os

    known_keys = _known_credential_vars()

    explicit_model = model is not None
    if model is None:
        model = default_model_for_available_provider()

    required_vars = _provider_key_vars_for_model(model)

    if required_vars:
        if any(os.environ.get(v) for v in required_vars):
            return True
        try:
            store = CredentialStore()
            providers = [p.lower() for p in store.list_providers()]
            wanted = _stored_providers_for_vars(required_vars)
            if any(p in providers for p in wanted):
                return True
        except Exception:
            pass
        if not explicit_model:
            try:
                endpoint = resolve_llm_endpoint_with_credentials()
                if endpoint.api_key:
                    return True
            except Exception:
                pass
        return False

    if any(os.environ.get(k) for k in known_keys):
        return True

    try:
        store = CredentialStore()
        if store.list_providers():
            return True
    except Exception:
        pass

    try:
        endpoint = resolve_llm_endpoint_with_credentials()
        return bool(endpoint.api_key)
    except Exception:
        pass

    return False
