"""
Tests for LLM Gateway Providers

Tests the gateway provider implementations for OpenRouter, LiteLLM Proxy,
and custom gateways.
"""

import pytest
import os
from unittest.mock import patch, MagicMock


class TestGatewayProviders:
    """Tests for gateway provider implementations."""
    
    def test_openrouter_provider_initialization(self):
        """Should initialize OpenRouter provider correctly."""
        from praisonai.llm.gateways import OpenRouterProvider
        
        provider = OpenRouterProvider("gpt-4", {"api_key": "test-key"})
        
        assert provider.model_id == "openrouter/gpt-4"
        assert provider.config["api_key"] == "test-key"
        assert provider.config["base_url"] == "https://openrouter.ai/api/v1"
    
    def test_openrouter_provider_env_var(self):
        """Should use OPENROUTER_API_KEY from environment."""
        from praisonai.llm.gateways import OpenRouterProvider
        
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "env-test-key"}):
            provider = OpenRouterProvider("claude-3.5-sonnet")
            assert provider.config["api_key"] == "env-test-key"
    
    def test_openrouter_model_prefix(self):
        """Should handle models with and without openrouter/ prefix."""
        from praisonai.llm.gateways import OpenRouterProvider
        
        # Without prefix
        provider1 = OpenRouterProvider("gpt-4")
        assert provider1.model_id == "openrouter/gpt-4"
        
        # With prefix (should not double-prefix)
        provider2 = OpenRouterProvider("openrouter/claude-3.5-sonnet")
        assert provider2.model_id == "openrouter/claude-3.5-sonnet"
    
    def test_litellm_proxy_provider_initialization(self):
        """Should initialize LiteLLM Proxy provider correctly."""
        from praisonai.llm.gateways import LiteLLMProxyProvider
        
        provider = LiteLLMProxyProvider("gpt-4", {"api_key": "test-key"})
        
        assert provider.model_id == "gpt-4"
        assert provider.config["api_key"] == "test-key"
        assert provider.config["base_url"] == "http://localhost:4000"
    
    def test_litellm_proxy_custom_base_url(self):
        """Should support custom base URL for LiteLLM Proxy."""
        from praisonai.llm.gateways import LiteLLMProxyProvider
        
        with patch.dict(os.environ, {"LITELLM_PROXY_BASE_URL": "https://my-proxy.com"}):
            provider = LiteLLMProxyProvider("gpt-4")
            assert provider.config["base_url"] == "https://my-proxy.com"
    
    def test_custom_gateway_provider_requires_base_url(self):
        """Should require base_url for custom gateway."""
        from praisonai.llm.gateways import CustomGatewayProvider
        
        with pytest.raises(ValueError, match="requires 'base_url'"):
            CustomGatewayProvider("gpt-4")
    
    def test_custom_gateway_provider_initialization(self):
        """Should initialize custom gateway with base_url."""
        from praisonai.llm.gateways import CustomGatewayProvider
        
        provider = CustomGatewayProvider(
            "my-model", 
            {"base_url": "https://api.example.com/v1", "api_key": "test-key"}
        )
        
        assert provider.model_id == "my-model"
        assert provider.config["base_url"] == "https://api.example.com/v1"
        assert provider.config["api_key"] == "test-key"
    
    @pytest.mark.skip(reason="litellm required for this test")
    @patch("litellm.completion")
    def test_gateway_generate_method(self, mock_completion):
        """Should call litellm.completion correctly."""
        from praisonai.llm.gateways import OpenRouterProvider
        
        # Setup mock
        mock_response = MagicMock()
        mock_completion.return_value = mock_response
        
        provider = OpenRouterProvider("gpt-4", {"api_key": "test-key"})
        result = provider.generate("Hello world")
        
        # Verify litellm was called correctly
        mock_completion.assert_called_once()
        call_args = mock_completion.call_args
        
        assert call_args.kwargs["model"] == "openrouter/gpt-4"
        assert call_args.kwargs["messages"] == [{"role": "user", "content": "Hello world"}]
        assert call_args.kwargs["api_key"] == "test-key"
        assert call_args.kwargs["base_url"] == "https://openrouter.ai/api/v1"
        assert result == mock_response
    
    def test_gateway_providers_registration(self):
        """Should register gateway providers in the registry."""
        from praisonai.llm import has_llm_provider, list_llm_providers
        
        # Check that gateway providers are registered
        assert has_llm_provider("openrouter")
        assert has_llm_provider("litellm-proxy")
        assert has_llm_provider("custom-gateway")
        
        # Check aliases
        assert has_llm_provider("or")  # OpenRouter alias
        assert has_llm_provider("llm-proxy")  # LiteLLM Proxy alias
        assert has_llm_provider("gateway")  # Custom gateway alias
    
    def test_create_provider_with_gateway(self):
        """Should create gateway provider instances via create_llm_provider."""
        from praisonai.llm import create_llm_provider
        
        # Test OpenRouter
        provider = create_llm_provider({
            "name": "openrouter",
            "model_id": "gpt-4",
            "config": {"api_key": "test-key"}
        })
        assert provider.provider_id == "openrouter"
        assert provider.model_id == "openrouter/gpt-4"
        
        # Test LiteLLM Proxy
        provider2 = create_llm_provider({
            "name": "litellm-proxy",
            "model_id": "claude-3",
            "config": {"api_key": "proxy-key"}
        })
        assert provider2.provider_id == "litellmproxy"
        assert provider2.model_id == "claude-3"