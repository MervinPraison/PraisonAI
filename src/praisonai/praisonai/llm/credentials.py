"""
LLM credential resolution bridge.

Bridges the credential store with LLM endpoint resolution to provide
seamless credential fallback when environment variables are not set.
"""

from typing import Optional, Dict, Any

from ..cli.configuration.credentials import CredentialStore
from .env import (
    resolve_llm_endpoint,
    LLMEndpoint,
    default_model_for_available_provider,
)


def _credential_lookup(provider: str) -> Optional[Dict[str, Any]]:
    """
    Lookup function for credential fallback in LLM resolution.
    
    Args:
        provider: Provider name to lookup
        
    Returns:
        Credential dict if found, None otherwise
    """
    try:
        store = CredentialStore()
        credential = store.get_credential(provider)
        if credential:
            # Return only the minimal fields the LLM resolver needs. We avoid
            # ``asdict(credential)`` so OAuth internals (refresh_token,
            # access_token, token_url, client_id) never cross this boundary.
            data: Dict[str, Any] = {
                "provider": credential.provider,
                "api_key": credential.api_key,
                "base_url": credential.base_url,
                "model": credential.model,
                "metadata": credential.metadata,
            }
            # For OAuth, surface a freshly-refreshed token through ``api_key``
            # so the resolver injects a valid secret transparently.
            if credential.is_oauth():
                data["api_key"] = store.get_valid_token(provider)
            return data
    except Exception:
        # Ignore errors in credential lookup to avoid breaking LLM resolution
        pass
    return None


def resolve_llm_endpoint_with_credentials(
    *, 
    default_base: str = "https://api.openai.com/v1",
    validate_model: bool = False
) -> LLMEndpoint:
    """
    Resolve LLM endpoint configuration with credential store fallback.
    
    This is the main entry point for resolving LLM configuration in the wrapper.
    It tries environment variables first, then falls back to stored credentials.
    
    Args:
        default_base: Default base URL if none found anywhere
        validate_model: Whether to validate the model ID (default: False)
        
    Returns:
        LLMEndpoint with resolved configuration
    """
    return resolve_llm_endpoint(
        default_base=default_base,
        fallback_lookup=_credential_lookup,
        validate_model=validate_model
    )


def inject_credentials_into_env() -> bool:
    """
    Inject stored credentials into the process environment.
    
    This function exports resolved API keys from the credential store
    into the process environment variables so that the core SDK can
    access them without modification.
    
    Returns:
        True if any credentials were injected, False otherwise
    """
    import os
    
    try:
        store = CredentialStore()
        providers = store.list_providers()
        injected = False
        
        # Map provider names to environment variable names
        env_mappings = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY", 
            "google": "GOOGLE_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "tavily": "TAVILY_API_KEY",
            "groq": "GROQ_API_KEY",
            "cohere": "COHERE_API_KEY",
        }
        
        for provider in providers:
            env_var = env_mappings.get(provider.lower())
            if not env_var:
                continue
                
            # Don't override existing environment variables
            if os.environ.get(env_var):
                continue
                
            credential = store.get_credential(provider)
            if not credential:
                continue

            # For OAuth credentials, rely solely on the refreshed token from the
            # store (which returns None when expired and refresh fails) so a
            # stale mirrored token is never injected. API keys fall back to the
            # stored key unchanged.
            if credential.is_oauth():
                token = store.get_valid_token(provider)
            else:
                token = credential.api_key
            if token:
                os.environ[env_var] = token
                injected = True
                
                # Also set base URL if provided
                if provider.lower() == "openai" and credential.base_url:
                    if not os.environ.get("OPENAI_BASE_URL"):
                        os.environ["OPENAI_BASE_URL"] = credential.base_url
                        
        return injected
        
    except Exception:
        # Ignore errors to avoid breaking the application
        return False


def _provider_key_vars_for_model(model: str) -> tuple[str, ...]:
    """
    Map a model id to the environment variable(s) that satisfy its provider.

    Returns an empty tuple when the provider cannot be determined, in which
    case the caller should treat any known credential as acceptable.
    """
    m = model.lower()
    # Explicit provider prefixes take precedence. The required var must match
    # what resolve_llm_endpoint()'s _PROVIDER_MAP reads for the same prefix, or
    # the gate and the resolver disagree (gate passes, runtime gets no key).
    if m.startswith("anthropic/") or m.startswith("claude"):
        return ("ANTHROPIC_API_KEY",)
    # google/ routes to GOOGLE_API_KEY in the resolver; gemini/ (and bare
    # "gemini") routes to GEMINI_API_KEY. Keep them distinct so the gate is
    # exactly what the endpoint will require at run time.
    if m.startswith("google/"):
        return ("GOOGLE_API_KEY",)
    if m.startswith("gemini/") or m.startswith("gemini"):
        return ("GEMINI_API_KEY",)
    if m.startswith("groq/"):
        return ("GROQ_API_KEY",)
    if m.startswith("cohere/"):
        return ("COHERE_API_KEY",)
    if m.startswith("ollama/"):
        return ("OLLAMA_HOST",)
    # OpenAI chat + reasoning families (gpt-*, o1/o3/o4-*) and explicit prefix.
    if (
        m.startswith("gpt")
        or m.startswith("o1")
        or m.startswith("o3")
        or m.startswith("o4")
        or m.startswith("openai/")
    ):
        return ("OPENAI_API_KEY",)
    return ()


# Map credential env-var names to the credential-store provider names that
# satisfy them, used to keep the stored-credential check provider-scoped.
_VAR_TO_STORED_PROVIDERS = {
    "OPENAI_API_KEY": ("openai",),
    "ANTHROPIC_API_KEY": ("anthropic",),
    "GEMINI_API_KEY": ("gemini", "google"),
    "GOOGLE_API_KEY": ("google", "gemini"),
    "GROQ_API_KEY": ("groq",),
    "COHERE_API_KEY": ("cohere",),
    "OLLAMA_HOST": ("ollama",),
}


def _stored_providers_for_vars(vars_: tuple[str, ...]) -> tuple[str, ...]:
    """Return the stored-credential provider names matching the given env-vars."""
    out: list[str] = []
    for v in vars_:
        out.extend(_VAR_TO_STORED_PROVIDERS.get(v, ()))
    return tuple(out)


def is_configured(model: Optional[str] = None) -> bool:
    """
    Check if credentials are configured for the specified or default model.
    
    This checks both environment variables and stored credentials to determine
    if the user has configured any usable API keys.
    
    Args:
        model: Optional model name to check for specific provider credentials.
               If not provided, the provider-aware default model is inferred
               from available credentials so the gate and the chosen model
               agree.
    
    Returns:
        True if credentials are available, False otherwise
    """
    import os
    
    # Check environment variables first
    known_keys = (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
        "GEMINI_API_KEY", "GROQ_API_KEY", "COHERE_API_KEY",
        "OLLAMA_HOST",  # Ollama doesn't need an API key
    )

    # When no model is given, infer the provider-aware default so the gate
    # agrees with what resolve_llm_endpoint() would actually pick. Remember
    # whether the caller supplied the model explicitly so an *inferred* default
    # can still defer to the resolver (which also consults stored credentials).
    explicit_model = model is not None
    if model is None:
        model = default_model_for_available_provider()

    required_vars = _provider_key_vars_for_model(model)

    # Known provider: the gate is strictly provider-scoped so it agrees with
    # the model that will actually be used. We do NOT accept an unrelated
    # credential (the original bug, e.g. only OPENAI_API_KEY for a Claude
    # model passing the gate and then failing at run time).
    if required_vars:
        if any(os.environ.get(v) for v in required_vars):
            return True
        # Check stored credentials for the matching provider only.
        try:
            store = CredentialStore()
            providers = [p.lower() for p in store.list_providers()]
            wanted = _stored_providers_for_vars(required_vars)
            if any(p in providers for p in wanted):
                return True
        except Exception:
            pass
        # The required provider was inferred from a default (no explicit model):
        # defer to the resolver so a stored credential for a *different*
        # provider can still satisfy the gate (it also picks the matching
        # default model at run time). An explicitly requested model stays
        # strictly gated to its own provider.
        if not explicit_model:
            try:
                endpoint = resolve_llm_endpoint_with_credentials()
                if endpoint.api_key:
                    return True
            except Exception:
                pass
        return False

    # Unknown provider: any known credential (env or stored) is acceptable.
    if any(os.environ.get(k) for k in known_keys):
        return True

    try:
        store = CredentialStore()
        if store.list_providers():
            return True
    except Exception:
        pass

    # Finally, check if we can resolve an endpoint with credentials.
    try:
        endpoint = resolve_llm_endpoint_with_credentials()
        return bool(endpoint.api_key)
    except Exception:
        pass

    return False