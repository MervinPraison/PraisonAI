"""Factory for creating appropriate LLM providers"""

import os
from typing import Optional, Union, Dict, Any
from .base import LLMProvider
from .openai_provider import OpenAIProvider
from .litellm_provider import LiteLLMProvider


class ProviderFactory:
    """Factory for creating appropriate LLM providers based on configuration."""
    
    @staticmethod
    def create(
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        provider: Optional[str] = None,
        **kwargs
    ) -> LLMProvider:
        """
        Create appropriate provider based on configuration.
        
        Args:
            model: Model name (e.g., "gpt-4", "anthropic/claude-3")
            api_key: API key for the provider
            base_url: Base URL for API calls
            provider: Force specific provider ("openai", "litellm", "auto")
            **kwargs: Additional provider-specific arguments
        
        Returns:
            LLMProvider instance
        """
        # Use environment variables as defaults
        model = model or os.getenv('OPENAI_MODEL_NAME', 'gpt-4o')
        provider = provider or os.getenv('PRAISONAI_LLM_PROVIDER', 'auto')
        
        # Normalize provider name
        provider = provider.lower()
        
        # Determine provider
        if provider == "openai":
            # Force lightweight OpenAI provider
            return OpenAIProvider(api_key=api_key, base_url=base_url, **kwargs)
            
        elif provider == "litellm":
            # Force full-featured LiteLLM provider
            return LiteLLMProvider(
                model=model,
                api_key=api_key,
                base_url=base_url,
                **kwargs
            )
            
        else:
            # Auto-detect based on model string and configuration
            if _is_openai_model(model) and not _requires_litellm(model, base_url, kwargs):
                # Use lightweight provider for standard OpenAI models
                try:
                    return OpenAIProvider(api_key=api_key, base_url=base_url, **kwargs)
                except ImportError:
                    # Fallback to LiteLLM if OpenAI SDK not installed
                    return LiteLLMProvider(
                        model=model,
                        api_key=api_key,
                        base_url=base_url,
                        **kwargs
                    )
            else:
                # Use LiteLLM for multi-provider support
                return LiteLLMProvider(
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                    **kwargs
                )


def _is_openai_model(model: str) -> bool:
    """
    Check if model is a standard OpenAI model.
    
    Args:
        model: Model name
        
    Returns:
        True if it's an OpenAI model without provider prefix
    """
    if not model:
        return True  # Default to OpenAI
    
    # Check for provider prefixes (indicates non-OpenAI)
    if '/' in model:
        return False
    
    # OpenAI model patterns
    openai_patterns = [
        'gpt-3.5', 'gpt-4', 'o1-', 'text-', 
        'davinci', 'curie', 'babbage', 'ada'
    ]
    
    return any(model.startswith(pattern) for pattern in openai_patterns)


def _requires_litellm(model: str, base_url: Optional[str], kwargs: Dict[str, Any]) -> bool:
    """
    Check if configuration requires LiteLLM instead of direct OpenAI.
    
    Args:
        model: Model name
        base_url: Base URL if provided
        kwargs: Additional configuration
        
    Returns:
        True if LiteLLM is required
    """
    # Check for non-OpenAI base URLs (like Ollama)
    if base_url:
        ollama_indicators = ['localhost:11434', '127.0.0.1:11434', ':11434']
        if any(indicator in base_url for indicator in ollama_indicators):
            return True
    
    # Check for provider-specific parameters
    litellm_params = [
        'azure', 'azure_deployment', 'vertex_project', 'vertex_location',
        'aws_access_key_id', 'aws_secret_access_key', 'aws_region',
        'custom_llm_provider'
    ]
    
    if any(param in kwargs for param in litellm_params):
        return True
    
    # Check environment for non-OpenAI providers
    non_openai_env_vars = [
        'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'COHERE_API_KEY',
        'AZURE_API_KEY', 'VERTEX_PROJECT', 'AWS_ACCESS_KEY_ID'
    ]
    
    return any(os.getenv(var) for var in non_openai_env_vars)