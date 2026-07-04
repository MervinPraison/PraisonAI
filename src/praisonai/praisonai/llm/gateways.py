"""
LLM Gateway Providers for PraisonAI

This module provides pre-configured gateway providers for popular AI gateways
like LiteLLM.ai, OpenRouter.ai, and others. These gateways provide unified
access to 100+ LLM providers through OpenAI-compatible endpoints.

Example usage:
    from praisonai.llm import create_llm_provider
    
    # Use OpenRouter gateway
    provider = create_llm_provider("openrouter/meta-llama/llama-3.2-3b-instruct")
    
    # Use LiteLLM gateway
    provider = create_llm_provider("litellm-proxy/gpt-4")
    
    # Use custom gateway with config
    provider = create_llm_provider({
        "name": "openrouter",
        "model_id": "anthropic/claude-3.5-sonnet",
        "config": {
            "api_key": "your-openrouter-key",
            "extra_headers": {
                "X-Title": "My App"
            }
        }
    })
"""

from typing import Optional, Dict, Any
import os


class GatewayProvider:
    """Base class for AI Gateway providers."""
    
    def __init__(self, model_id: str, config: Optional[Dict[str, Any]] = None):
        """Initialize gateway provider.
        
        Args:
            model_id: Model identifier (e.g., "gpt-4", "claude-3.5-sonnet")
            config: Optional configuration including api_key, base_url, headers
        """
        self.model_id = model_id
        # Create a shallow copy to avoid mutating caller's dict
        self.config = dict(config) if config else {}
        self.provider_id = self.__class__.__name__.lower().replace("provider", "")
        
        # Merge environment variables with config
        self._setup_config()
    
    def _setup_config(self):
        """Setup configuration with environment variable fallbacks."""
        # Default to environment variables if not provided
        if "api_key" not in self.config:
            env_key = f"{self.provider_id.upper()}_API_KEY"
            if env_key in os.environ:
                self.config["api_key"] = os.environ[env_key]
        
        # Set base_url from class default
        if "base_url" not in self.config and hasattr(self.__class__, "DEFAULT_BASE_URL"):
            self.config["base_url"] = self.__class__.DEFAULT_BASE_URL
    
    def _resolve_model_and_kwargs(self, prompt: str, **kwargs):
        """Helper to resolve model and kwargs for LiteLLM calls."""
        try:
            import litellm
        except ImportError as err:
            raise ImportError(
                f"LiteLLM is required for {self.provider_id} gateway. "
                "Install with: pip install litellm"
            ) from err
        
        # Prepare completion kwargs
        completion_kwargs = {**self.config, **kwargs}
        
        # Remove our custom keys that LiteLLM doesn't understand
        for key in ["provider", "gateway"]:
            completion_kwargs.pop(key, None)
        
        messages = [{"role": "user", "content": prompt}]
        return litellm, self.model_id, messages, completion_kwargs
    
    def generate(self, prompt: str, **kwargs):
        """Generate completion using the gateway."""
        litellm, model_id, messages, completion_kwargs = self._resolve_model_and_kwargs(prompt, **kwargs)
        return litellm.completion(
            model=model_id,
            messages=messages,
            **completion_kwargs
        )
    
    async def generate_async(self, prompt: str, **kwargs):
        """Generate async completion using the gateway."""
        litellm, model_id, messages, completion_kwargs = self._resolve_model_and_kwargs(prompt, **kwargs)
        return await litellm.acompletion(
            model=model_id,
            messages=messages,
            **completion_kwargs
        )


class OpenRouterProvider(GatewayProvider):
    """OpenRouter.ai gateway provider.
    
    OpenRouter provides access to 100+ models from various providers
    through a unified API with automatic fallbacks and routing.
    
    Environment variable: OPENROUTER_API_KEY
    """
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    
    def _setup_config(self):
        """Setup OpenRouter-specific configuration."""
        super()._setup_config()
        
        # OpenRouter uses "openrouter/" prefix for models
        if not self.model_id.startswith("openrouter/"):
            self.model_id = f"openrouter/{self.model_id}"


class LiteLLMProxyProvider(GatewayProvider):
    """LiteLLM Proxy gateway provider.
    
    LiteLLM Proxy is a self-hosted or cloud gateway that provides
    caching, fallbacks, and load balancing for LLM calls.
    
    Environment variables: 
    - LITELLM_PROXY_API_KEY
    - LITELLM_PROXY_BASE_URL (default: http://localhost:4000)
    """
    DEFAULT_BASE_URL = "http://localhost:4000"
    
    def __init__(self, model_id: str, config: Optional[Dict[str, Any]] = None):
        """Initialize LiteLLM Proxy provider."""
        super().__init__(model_id, config)
        # Override provider_id to match registration key
        self.provider_id = "litellm-proxy"
    
    def _setup_config(self):
        """Setup LiteLLM Proxy configuration."""
        # Check for custom environment variables
        if "api_key" not in self.config:
            if "LITELLM_PROXY_API_KEY" in os.environ:
                self.config["api_key"] = os.environ["LITELLM_PROXY_API_KEY"]
        
        if "base_url" not in self.config:
            if "LITELLM_PROXY_BASE_URL" in os.environ:
                self.config["base_url"] = os.environ["LITELLM_PROXY_BASE_URL"]
            else:
                self.config["base_url"] = self.DEFAULT_BASE_URL


class CustomGatewayProvider(GatewayProvider):
    """Custom gateway provider for any OpenAI-compatible endpoint.
    
    Use this for custom gateways or self-hosted solutions that
    provide OpenAI-compatible APIs.
    """
    
    def __init__(self, model_id: str, config: Optional[Dict[str, Any]] = None):
        """Initialize custom gateway.
        
        Args:
            model_id: Model identifier
            config: Must include 'base_url' and optionally 'api_key'
        """
        super().__init__(model_id, config)
        
        if "base_url" not in self.config:
            raise ValueError(
                "CustomGatewayProvider requires 'base_url' in config. "
                "Example: {'base_url': 'https://api.example.com/v1'}"
            )


def register_gateway_providers():
    """Register all gateway providers with the LLM registry.
    
    This function is called automatically when the module is imported
    to register gateway providers with the default registry.
    """
    from .registry import register_llm_provider
    
    # Register OpenRouter
    register_llm_provider(
        "openrouter", 
        OpenRouterProvider,
        aliases=["or"],
        override=True
    )
    
    # Register LiteLLM Proxy (different from built-in litellm)
    register_llm_provider(
        "litellm-proxy",
        LiteLLMProxyProvider,
        aliases=["llm-proxy", "litellm-gateway"],
        override=True
    )
    
    # Register custom gateway
    register_llm_provider(
        "custom-gateway",
        CustomGatewayProvider,
        aliases=["gateway", "custom"],
        override=True
    )


# NOTE: Gateway providers are NOT auto-registered on import. Registration is
# driven lazily on first default-registry access via
# registry._ensure_gateways_registered(), which calls register_gateway_providers()
# exactly once. Re-adding a module-level call here would (a) double-register on
# every cold start and (b) reintroduce the eager import cost this deferral removes.