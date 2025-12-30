"""
LLM Provider Registry - Extensible provider registration system for Python.

This module provides parity with the TypeScript ProviderRegistry,
allowing users to register custom LLM providers that can be resolved by name.

Example:
    from praisonai.llm import register_llm_provider, create_llm_provider
    
    class CloudflareProvider:
        provider_id = "cloudflare"
        def __init__(self, model_id, config=None):
            self.model_id = model_id
            self.config = config or {}
        def generate(self, prompt):
            # Implementation
            pass
    
    register_llm_provider("cloudflare", CloudflareProvider)
    provider = create_llm_provider("cloudflare/workers-ai")
"""

from typing import Any, Callable, Dict, List, Optional, Type, Union


# Type aliases
ProviderClass = Type[Any]  # Class with __init__(model_id, config)
ProviderFactory = Callable[[str, Optional[Dict[str, Any]]], Any]
ProviderType = Union[ProviderClass, ProviderFactory]


class LLMProviderRegistry:
    """
    Registry for LLM providers.
    
    Manages registration and resolution of LLM providers by name.
    Supports lazy loading, aliases, and isolated instances.
    """
    
    def __init__(self):
        """Initialize an empty registry."""
        self._providers: Dict[str, ProviderType] = {}
        self._aliases: Dict[str, str] = {}  # alias -> canonical name
    
    def register(
        self,
        name: str,
        provider: ProviderType,
        *,
        override: bool = False,
        aliases: Optional[List[str]] = None
    ) -> None:
        """
        Register a provider by name.
        
        Args:
            name: Provider name (e.g., 'cloudflare', 'ollama')
            provider: Provider class or factory function
            override: Allow overwriting existing registration
            aliases: Additional names that resolve to this provider
            
        Raises:
            ValueError: If name is already registered (unless override=True)
        """
        normalized_name = name.lower()
        
        # Check for existing registration
        if normalized_name in self._providers and not override:
            raise ValueError(
                f"Provider '{name}' is already registered. "
                f"Use override=True to replace it."
            )
        
        self._providers[normalized_name] = provider
        
        # Register aliases
        if aliases:
            for alias in aliases:
                normalized_alias = alias.lower()
                # Check collision with existing provider name
                if normalized_alias in self._providers and not override:
                    raise ValueError(
                        f"Alias '{alias}' conflicts with existing provider name. "
                        f"Use override=True to replace it."
                    )
                # Check collision with existing alias
                if normalized_alias in self._aliases and not override:
                    existing_target = self._aliases[normalized_alias]
                    raise ValueError(
                        f"Alias '{alias}' is already registered (points to '{existing_target}'). "
                        f"Use override=True to replace it."
                    )
                self._aliases[normalized_alias] = normalized_name
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a provider by name.
        
        Args:
            name: Provider name to unregister
            
        Returns:
            True if provider was unregistered, False if not found
        """
        normalized_name = name.lower()
        
        # Check if it's an alias
        if normalized_name in self._aliases:
            del self._aliases[normalized_name]
            return True
        
        # Check if it's a canonical name
        if normalized_name in self._providers:
            # Remove all aliases pointing to this provider
            aliases_to_remove = [
                alias for alias, canonical in self._aliases.items()
                if canonical == normalized_name
            ]
            for alias in aliases_to_remove:
                del self._aliases[alias]
            
            del self._providers[normalized_name]
            return True
        
        return False
    
    def has(self, name: str) -> bool:
        """
        Check if a provider is registered.
        
        Args:
            name: Provider name to check
            
        Returns:
            True if provider is registered
        """
        normalized_name = name.lower()
        return normalized_name in self._providers or normalized_name in self._aliases
    
    def list(self) -> List[str]:
        """
        List all registered provider names (canonical names only).
        
        Returns:
            List of provider names
        """
        return list(self._providers.keys())
    
    def list_all(self) -> List[str]:
        """
        List all names including aliases.
        
        Returns:
            List of all registered names and aliases
        """
        return list(self._providers.keys()) + list(self._aliases.keys())
    
    def resolve(
        self,
        name: str,
        model_id: str,
        config: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Resolve a provider by name, creating an instance.
        
        Args:
            name: Provider name
            model_id: Model ID to pass to constructor
            config: Optional provider config
            
        Returns:
            Provider instance
            
        Raises:
            ValueError: If provider not found
        """
        normalized_name = name.lower()
        
        # Resolve alias to canonical name
        canonical_name = self._aliases.get(normalized_name, normalized_name)
        
        provider = self._providers.get(canonical_name)
        if provider is None:
            available = self.list()
            raise ValueError(
                f"Unknown provider: '{name}'. "
                f"Available providers: {', '.join(available) if available else 'none'}. "
                f"Register a custom provider with register_llm_provider('{name}', YourProviderClass)."
            )
        
        # Create instance
        return provider(model_id, config)
    
    def get(self, name: str) -> Optional[ProviderType]:
        """
        Get the provider class/factory without instantiating.
        
        Args:
            name: Provider name
            
        Returns:
            Provider class/factory or None
        """
        normalized_name = name.lower()
        canonical_name = self._aliases.get(normalized_name, normalized_name)
        return self._providers.get(canonical_name)


# ============================================================================
# Default Registry Singleton
# ============================================================================

_default_registry: Optional[LLMProviderRegistry] = None


def get_default_llm_registry() -> LLMProviderRegistry:
    """
    Get the default global LLM provider registry.
    
    This is the registry used by create_llm_provider() when no custom registry
    is specified.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = LLMProviderRegistry()
        _register_builtin_providers(_default_registry)
    return _default_registry


def _register_builtin_providers(registry: LLMProviderRegistry) -> None:
    """
    Register built-in providers to a registry.
    
    Uses lazy loading to avoid importing heavy dependencies at module load time.
    """
    # Note: In Python, the actual LLM providers are in praisonaiagents.llm
    # which uses LiteLLM. This registry is for custom provider extensions.
    # Built-in providers are handled by LiteLLM automatically.
    pass


def register_llm_provider(
    name: str,
    provider: ProviderType,
    *,
    override: bool = False,
    aliases: Optional[List[str]] = None
) -> None:
    """
    Register a provider to the default global registry.
    
    Example:
        from praisonai.llm import register_llm_provider
        
        class CloudflareProvider:
            provider_id = "cloudflare"
            def __init__(self, model_id, config=None):
                self.model_id = model_id
                self.config = config or {}
        
        register_llm_provider("cloudflare", CloudflareProvider)
    """
    get_default_llm_registry().register(name, provider, override=override, aliases=aliases)


def unregister_llm_provider(name: str) -> bool:
    """Unregister a provider from the default global registry."""
    return get_default_llm_registry().unregister(name)


def has_llm_provider(name: str) -> bool:
    """Check if a provider is registered in the default registry."""
    return get_default_llm_registry().has(name)


def list_llm_providers() -> List[str]:
    """List all providers in the default registry."""
    return get_default_llm_registry().list()


# ============================================================================
# Provider Creation
# ============================================================================

def parse_model_string(model: str) -> Dict[str, str]:
    """
    Parse model string into provider and model ID.
    
    Supports formats:
    - "provider/model" (e.g., "openai/gpt-4o")
    - "model" (defaults based on prefix)
    
    Args:
        model: Model string
        
    Returns:
        Dict with 'provider_id' and 'model_id' keys
    """
    if "/" in model:
        parts = model.split("/", 1)
        return {"provider_id": parts[0].lower(), "model_id": parts[1]}
    
    # Default based on model prefix
    model_lower = model.lower()
    if model_lower.startswith("gpt-") or model_lower.startswith("o1") or model_lower.startswith("o3"):
        return {"provider_id": "openai", "model_id": model}
    if model_lower.startswith("claude-"):
        return {"provider_id": "anthropic", "model_id": model}
    if model_lower.startswith("gemini-"):
        return {"provider_id": "google", "model_id": model}
    
    # Default to openai
    return {"provider_id": "openai", "model_id": model}


def create_llm_provider(
    input_value: Union[str, Dict[str, Any], Any],
    *,
    registry: Optional[LLMProviderRegistry] = None,
    config: Optional[Dict[str, Any]] = None
) -> Any:
    """
    Create a provider instance from various input types.
    
    Args:
        input_value: One of:
            - String: "provider/model" or "model"
            - Dict: {"name": "provider", "model_id": "model", "config": {...}}
            - Provider instance: passed through
        registry: Optional custom registry (defaults to global)
        config: Optional provider config
        
    Returns:
        Provider instance
        
    Example:
        # String input
        provider = create_llm_provider("openai/gpt-4o")
        
        # Custom provider (after registration)
        register_llm_provider("cloudflare", CloudflareProvider)
        provider = create_llm_provider("cloudflare/workers-ai")
        
        # Provider instance (pass-through)
        provider = create_llm_provider(existing_provider)
        
        # Spec dict
        provider = create_llm_provider({
            "name": "openai",
            "model_id": "gpt-4o",
            "config": {"timeout": 5000}
        })
    """
    reg = registry or get_default_llm_registry()
    
    # Case 1: Already a provider instance (has provider_id and model_id)
    if hasattr(input_value, "provider_id") and hasattr(input_value, "model_id"):
        return input_value
    
    # Case 2: Spec dict
    if isinstance(input_value, dict) and "name" in input_value:
        name = input_value["name"]
        model_id = input_value.get("model_id", "default")
        provider_config = input_value.get("config") or config
        return reg.resolve(name, model_id, provider_config)
    
    # Case 3: String - parse and resolve
    if isinstance(input_value, str):
        parsed = parse_model_string(input_value)
        return reg.resolve(parsed["provider_id"], parsed["model_id"], config)
    
    raise ValueError(
        f"Invalid provider input. Expected string, provider instance, or spec dict. "
        f"Got: {type(input_value).__name__}"
    )


def _reset_default_registry() -> None:
    """Reset the default registry (mainly for testing)."""
    global _default_registry
    _default_registry = None
