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
import threading
from .._registry import PluginRegistry


# Type aliases
ProviderClass = Type[Any]  # Class with __init__(model_id, config)
ProviderFactory = Callable[[str, Optional[Dict[str, Any]]], Any]
ProviderType = Union[ProviderClass, ProviderFactory]


class LLMProviderRegistry(PluginRegistry[ProviderType]):
    """
    Registry for LLM providers.
    
    Manages registration and resolution of LLM providers by name.
    Supports lazy loading, aliases, and isolated instances.
    Thread-safe for concurrent operations.
    
    Now inherits from PluginRegistry to eliminate duplication.
    """
    
    def __init__(self):
        """Initialize LLM provider registry."""
        # Get built-in provider loaders
        builtins = _get_builtin_provider_loaders()
        
        # Initialize parent with entry points and builtins
        super().__init__(
            entry_point_group="praisonai.llm_providers",
            builtins=builtins
        )
        
        # Register aliases for built-in providers
        self._register_builtin_aliases()
    
    def _register_builtin_aliases(self) -> None:
        """Register aliases for built-in providers."""
        aliases_map = [
            ("openai", ("oai",)),
            ("anthropic", ("claude",)),
            ("google", ("gemini", "google_genai")),
        ]
        
        with self._lock:
            for name, aliases in aliases_map:
                if name in self._items:  # Only add aliases if the provider loaded
                    for alias in aliases:
                        self._aliases[alias.lower()] = name.lower()
    
    def resolve_provider(
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
        provider_cls = self.resolve(name)
        # Create instance outside the lock
        return provider_cls(model_id, config)

    def register_provider(
        self,
        name: str,
        provider: ProviderType,
        *,
        override: bool = False,
        aliases: Optional[List[str]] = None
    ) -> None:
        """
        Register a provider by name with override validation.
        
        Args:
            name: Provider name (e.g., 'cloudflare', 'ollama')
            provider: Provider class or factory function
            override: Allow overwriting existing registration
            aliases: Additional names that resolve to this provider
            
        Raises:
            ValueError: If name is already registered (unless override=True)
        """
        # Check for existing registration if override is False
        if not override and self.is_available(name):
            raise ValueError(
                f"Provider '{name}' is already registered. "
                f"Use override=True to replace it."
            )
        
        # Check alias conflicts if override is False
        if not override and aliases:
            for alias in aliases:
                if self.is_available(alias):
                    raise ValueError(
                        f"Alias '{alias}' is already registered. "
                        f"Use override=True to replace it."
                    )
        
        # If override=True, unregister existing entries first
        if override:
            self.unregister(name)
            if aliases:
                for alias in aliases:
                    self.unregister(alias)
        
        # Use parent class registration
        self.register(name, provider, aliases=aliases)
    
    # Inherit unregister, is_available, list_names from parent
    # Add backwards compatibility aliases
    def has(self, name: str) -> bool:
        """Check if a provider is registered (alias for is_available)."""
        return self.is_available(name)
    
    def list(self) -> List[str]:
        """List provider names (alias for list_names)."""
        return self.list_names()
    
    def list_all(self) -> List[str]:
        """List all names including aliases (alias for list_all_names)."""
        return self.list_all_names()
    
    def get(self, name: str) -> Optional[ProviderType]:
        """
        Get the provider class/factory without instantiating.
        
        Args:
            name: Provider name
            
        Returns:
            Provider class/factory or None
        """
        try:
            return self.resolve(name)
        except ValueError:
            return None


# ============================================================================
# Default Registry Instance (No Singleton)
# ============================================================================

# Default module-level registry instance
_default_llm_registry: Optional[LLMProviderRegistry] = None
_default_llm_lock = threading.Lock()

def get_default_llm_registry() -> LLMProviderRegistry:
    """
    Get the default global LLM provider registry.
    
    This is the registry used by create_llm_provider() when no custom registry
    is specified. Uses lazy initialization pattern.
    """
    global _default_llm_registry
    if _default_llm_registry is None:
        with _default_llm_lock:
            if _default_llm_registry is None:
                _default_llm_registry = LLMProviderRegistry()
    return _default_llm_registry


def _get_builtin_provider_loaders() -> Dict[str, Callable[[], ProviderType]]:
    """
    Get built-in provider loaders.
    
    Returns a dict of name -> loader function that creates provider factories.
    Uses lazy loading to avoid importing heavy dependencies at module load time.
    """
    # Built-in adapter that wraps LiteLLM so create_llm_provider works out of the box.
    class _LiteLLMProvider:
        """Generic LiteLLM-backed provider used for openai/anthropic/google/etc."""
        def __init__(self, model_id: str, config: Optional[Dict[str, Any]] = None):
            self.provider_id = "litellm"
            self.model_id = model_id
            self.config = config or {}

        def _resolve_model_and_kwargs(self, prompt: str, **kwargs):
            """Helper to resolve model and kwargs for both sync and async methods."""
            try:
                import litellm  # lazy
            except ImportError as err:
                raise ImportError(
                    "LiteLLM is required for built-in providers. "
                    "Install with: pip install litellm"
                ) from err
            
            provider_prefix = self.config.get("provider", "")
            full_model = f"{provider_prefix}/{self.model_id}".strip("/") if provider_prefix else self.model_id
            completion_kwargs = {
                k: v for k, v in {**self.config, **kwargs}.items() if k != "provider"
            }
            messages = [{"role": "user", "content": prompt}]
            return litellm, full_model, messages, completion_kwargs

        def generate(self, prompt: str, **kwargs):
            """Sync variant — uses litellm.completion()."""
            litellm, full_model, messages, completion_kwargs = self._resolve_model_and_kwargs(prompt, **kwargs)
            return litellm.completion(
                model=full_model,
                messages=messages,
                **completion_kwargs,
            )

        async def generate_async(self, prompt: str, **kwargs):
            """Async variant — uses litellm.acompletion() to avoid blocking the event loop.
            
            generate() calls litellm.completion() which is a blocking network call.
            Calling it from an async context would stall the entire event loop.
            generate_async() uses litellm.acompletion() — the native async variant.
            """
            litellm, full_model, messages, completion_kwargs = self._resolve_model_and_kwargs(prompt, **kwargs)
            return await litellm.acompletion(
                model=full_model,
                messages=messages,
                **completion_kwargs,
            )

    def _make_litellm_factory(provider_prefix: str):
        def factory(model_id, config=None):
            cfg = dict(config or {})
            cfg.setdefault("provider", provider_prefix)
            return _LiteLLMProvider(model_id, cfg)
        return factory

    # Build loader dict for the canonical PluginRegistry
    loaders: Dict[str, Callable[[], ProviderType]] = {}
    
    # Cover the providers parse_model_string() already special-cases.
    for name, aliases in [
        ("openai",    ("oai",)),
        ("anthropic", ("claude",)),
        ("google",    ("gemini", "google_genai")),
    ]:
        # Use local function to capture name correctly in closure
        def make_loader(provider_name):
            return lambda: _make_litellm_factory(provider_name)
        loaders[name] = make_loader(name)
        # Note: aliases will be registered separately via PluginRegistry.register()
    
    return loaders


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
    get_default_llm_registry().register_provider(name, provider, override=override, aliases=aliases)


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
        return reg.resolve_provider(name, model_id, provider_config)
    
    # Case 3: String - parse and resolve
    if isinstance(input_value, str):
        parsed = parse_model_string(input_value)
        return reg.resolve_provider(parsed["provider_id"], parsed["model_id"], config)
    
    raise ValueError(
        f"Invalid provider input. Expected string, provider instance, or spec dict. "
        f"Got: {type(input_value).__name__}"
    )


def _reset_default_registry() -> None:
    """Reset the default registry (mainly for testing)."""
    global _default_llm_registry
    with _default_llm_lock:
        _default_llm_registry = None
