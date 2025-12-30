"""
LLM Provider Registry Unit Tests (TDD)

Tests for the extensible LLM provider registry that provides parity
with the TypeScript implementation for Issue #1095.
"""

import pytest
from typing import Any, Dict, Optional


class MockLLMProvider:
    """Mock LLM provider for testing."""
    
    provider_id = "mock"
    
    def __init__(self, model_id: str, config: Optional[Dict[str, Any]] = None):
        self.model_id = model_id
        self.config = config or {}
    
    def generate(self, prompt: str) -> str:
        return f"Mock response for: {prompt}"


class CustomCloudflareProvider:
    """Custom provider for testing registration."""
    
    provider_id = "cloudflare"
    
    def __init__(self, model_id: str, config: Optional[Dict[str, Any]] = None):
        self.model_id = model_id
        self.config = config or {}
    
    def generate(self, prompt: str) -> str:
        return f"Cloudflare response for: {prompt}"


class TestLLMProviderRegistry:
    """Tests for LLMProviderRegistry class."""
    
    def test_create_empty_registry(self):
        """Should create an empty registry."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry = LLMProviderRegistry()
        assert registry is not None
        assert registry.list() == []
    
    def test_register_provider_class(self):
        """Should register a provider class."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry = LLMProviderRegistry()
        registry.register("mock", MockLLMProvider)
        
        assert registry.has("mock")
        assert "mock" in registry.list()
    
    def test_register_provider_with_factory(self):
        """Should register a provider with a factory function."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry = LLMProviderRegistry()
        def factory(model_id, config=None):
            return MockLLMProvider(model_id, config)
        registry.register("mock", factory)
        
        assert registry.has("mock")
    
    def test_register_provider_with_aliases(self):
        """Should register provider with aliases."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry = LLMProviderRegistry()
        registry.register("cloudflare", CustomCloudflareProvider, aliases=["cf", "workers-ai"])
        
        assert registry.has("cloudflare")
        assert registry.has("cf")
        assert registry.has("workers-ai")
    
    def test_duplicate_registration_raises_error(self):
        """Should raise error on duplicate registration by default."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry = LLMProviderRegistry()
        registry.register("mock", MockLLMProvider)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register("mock", CustomCloudflareProvider)
    
    def test_override_registration(self):
        """Should allow override with explicit flag."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry = LLMProviderRegistry()
        registry.register("mock", MockLLMProvider)
        registry.register("mock", CustomCloudflareProvider, override=True)
        
        provider = registry.resolve("mock", "test-model")
        assert provider.provider_id == "cloudflare"
    
    def test_unregister_provider(self):
        """Should unregister a provider."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry = LLMProviderRegistry()
        registry.register("mock", MockLLMProvider)
        assert registry.has("mock")
        
        result = registry.unregister("mock")
        assert result is True
        assert not registry.has("mock")
    
    def test_unregister_nonexistent_returns_false(self):
        """Should return False when unregistering non-existent provider."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry = LLMProviderRegistry()
        result = registry.unregister("nonexistent")
        assert result is False
    
    def test_resolve_provider(self):
        """Should resolve a registered provider by name."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry = LLMProviderRegistry()
        registry.register("mock", MockLLMProvider)
        
        provider = registry.resolve("mock", "test-model")
        assert isinstance(provider, MockLLMProvider)
        assert provider.model_id == "test-model"
    
    def test_resolve_provider_with_config(self):
        """Should resolve provider with config."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry = LLMProviderRegistry()
        registry.register("mock", MockLLMProvider)
        
        config = {"api_key": "test-key", "timeout": 5000}
        provider = registry.resolve("mock", "test-model", config)
        assert provider.config == config
    
    def test_resolve_via_alias(self):
        """Should resolve provider via alias."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry = LLMProviderRegistry()
        registry.register("cloudflare", CustomCloudflareProvider, aliases=["cf"])
        
        provider = registry.resolve("cf", "workers-ai-model")
        assert provider.provider_id == "cloudflare"
    
    def test_resolve_unknown_provider_raises_error(self):
        """Should raise clear error for unknown provider."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry = LLMProviderRegistry()
        registry.register("openai", MockLLMProvider)
        registry.register("anthropic", MockLLMProvider)
        
        with pytest.raises(ValueError) as exc_info:
            registry.resolve("cloudflare", "model")
        
        error_msg = str(exc_info.value).lower()
        assert "unknown provider" in error_msg
        assert "cloudflare" in error_msg
        assert "openai" in error_msg or "anthropic" in error_msg


class TestDefaultRegistry:
    """Tests for default global registry."""
    
    def test_get_default_registry_singleton(self):
        """Should return the same registry instance."""
        from praisonai.llm.registry import get_default_llm_registry
        
        registry1 = get_default_llm_registry()
        registry2 = get_default_llm_registry()
        assert registry1 is registry2
    
    def test_register_provider_global(self):
        """Should register provider to default registry."""
        from praisonai.llm.registry import (
            register_llm_provider,
            unregister_llm_provider,
            get_default_llm_registry
        )
        
        register_llm_provider("custom-test", MockLLMProvider)
        assert get_default_llm_registry().has("custom-test")
        
        # Cleanup
        unregister_llm_provider("custom-test")
    
    def test_unregister_provider_global(self):
        """Should unregister provider from default registry."""
        from praisonai.llm.registry import (
            register_llm_provider,
            unregister_llm_provider,
            get_default_llm_registry
        )
        
        register_llm_provider("custom-test-2", MockLLMProvider)
        assert get_default_llm_registry().has("custom-test-2")
        
        unregister_llm_provider("custom-test-2")
        assert not get_default_llm_registry().has("custom-test-2")


class TestMultiAgentSafety:
    """Tests for multi-agent safety with isolated registries."""
    
    def test_isolated_registries(self):
        """Should support isolated registries per context."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry1 = LLMProviderRegistry()
        registry2 = LLMProviderRegistry()
        
        registry1.register("provider-a", MockLLMProvider)
        registry2.register("provider-b", CustomCloudflareProvider)
        
        assert registry1.has("provider-a")
        assert not registry1.has("provider-b")
        
        assert not registry2.has("provider-a")
        assert registry2.has("provider-b")
    
    def test_no_leak_between_registries(self):
        """Should not leak registrations between isolated registries."""
        from praisonai.llm.registry import LLMProviderRegistry
        
        registry1 = LLMProviderRegistry()
        registry2 = LLMProviderRegistry()
        
        registry1.register("shared-name", MockLLMProvider)
        registry2.register("shared-name", CustomCloudflareProvider)
        
        provider1 = registry1.resolve("shared-name", "model")
        provider2 = registry2.resolve("shared-name", "model")
        
        assert provider1.provider_id == "mock"
        assert provider2.provider_id == "cloudflare"


class TestCreateLLMProvider:
    """Tests for create_llm_provider function."""
    
    def test_create_from_string(self):
        """Should create provider from string."""
        from praisonai.llm.registry import (
            create_llm_provider,
            register_llm_provider,
            unregister_llm_provider
        )
        
        register_llm_provider("mock", MockLLMProvider)
        
        try:
            provider = create_llm_provider("mock/test-model")
            assert provider.provider_id == "mock"
            assert provider.model_id == "test-model"
        finally:
            unregister_llm_provider("mock")
    
    def test_create_from_instance(self):
        """Should pass through provider instance."""
        from praisonai.llm.registry import create_llm_provider
        
        instance = MockLLMProvider("direct-model")
        provider = create_llm_provider(instance)
        
        assert provider is instance
        assert provider.model_id == "direct-model"
    
    def test_create_from_spec_dict(self):
        """Should create provider from spec dict."""
        from praisonai.llm.registry import (
            create_llm_provider,
            register_llm_provider,
            unregister_llm_provider
        )
        
        register_llm_provider("mock", MockLLMProvider)
        
        try:
            provider = create_llm_provider({
                "name": "mock",
                "model_id": "spec-model",
                "config": {"timeout": 5000}
            })
            assert provider.provider_id == "mock"
            assert provider.model_id == "spec-model"
        finally:
            unregister_llm_provider("mock")
    
    def test_create_with_custom_registry(self):
        """Should use custom registry when provided."""
        from praisonai.llm.registry import create_llm_provider, LLMProviderRegistry
        
        custom_registry = LLMProviderRegistry()
        custom_registry.register("isolated", CustomCloudflareProvider)
        
        provider = create_llm_provider("isolated/model", registry=custom_registry)
        assert provider.provider_id == "cloudflare"
        
        # Should not be in default registry
        with pytest.raises(ValueError):
            create_llm_provider("isolated/model")
