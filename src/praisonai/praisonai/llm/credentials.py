"""
LLM credential resolution bridge.

Bridges the credential store with LLM endpoint resolution to provide
seamless credential fallback when environment variables are not set.
"""

from typing import Optional, Dict, Any
from dataclasses import asdict

from ..cli.configuration.credentials import CredentialStore
from .env import resolve_llm_endpoint, LLMEndpoint


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
            return asdict(credential)
    except Exception:
        # Ignore errors in credential lookup to avoid breaking LLM resolution
        pass
    return None


def resolve_llm_endpoint_with_credentials(*, default_base: str = "https://api.openai.com/v1") -> LLMEndpoint:
    """
    Resolve LLM endpoint configuration with credential store fallback.
    
    This is the main entry point for resolving LLM configuration in the wrapper.
    It tries environment variables first, then falls back to stored credentials.
    
    Args:
        default_base: Default base URL if none found anywhere
        
    Returns:
        LLMEndpoint with resolved configuration
    """
    return resolve_llm_endpoint(
        default_base=default_base,
        fallback_lookup=_credential_lookup
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
            if credential and credential.api_key:
                os.environ[env_var] = credential.api_key
                injected = True
                
                # Also set base URL if provided
                if provider.lower() == "openai" and credential.base_url:
                    if not os.environ.get("OPENAI_BASE_URL"):
                        os.environ["OPENAI_BASE_URL"] = credential.base_url
                        
        return injected
        
    except Exception:
        # Ignore errors to avoid breaking the application
        return False


def is_configured(model: Optional[str] = None) -> bool:
    """
    Check if credentials are configured for the specified or default model.
    
    This checks both environment variables and stored credentials to determine
    if the user has configured any usable API keys.
    
    Args:
        model: Optional model name to check for specific provider credentials.
               If not provided, checks for any configured credentials.
    
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
    
    # If any env var is set, consider it configured
    if any(os.environ.get(k) for k in known_keys):
        return True
    
    # Check stored credentials
    try:
        store = CredentialStore()
        providers = store.list_providers()
        
        # If we have any stored credentials, we're configured
        if providers:
            # If model is specified, check for that specific provider
            if model:
                # Map model prefixes to providers
                model_lower = model.lower()
                if model_lower.startswith("gpt"):
                    return "openai" in [p.lower() for p in providers]
                elif model_lower.startswith("claude"):
                    return "anthropic" in [p.lower() for p in providers]
                elif model_lower.startswith("gemini"):
                    return "google" in [p.lower() for p in providers] or "gemini" in [p.lower() for p in providers]
                elif model_lower.startswith("llama") or model_lower.startswith("mistral"):
                    # Could be Ollama or Groq
                    return "ollama" in [p.lower() for p in providers] or "groq" in [p.lower() for p in providers]
            
            # Any stored credential means we're configured
            return True
            
    except Exception:
        # If we can't check stored credentials, fall back to env check
        pass
    
    # Finally, check if we can resolve an endpoint with credentials
    try:
        endpoint = resolve_llm_endpoint_with_credentials()
        return bool(endpoint.api_key)
    except Exception:
        pass
    
    return False