#!/usr/bin/env python
"""
Unit tests for ProviderRegistry backward compatibility.

Tests that the ProviderRegistry architectural refactor maintains 100% backward
compatibility with existing APIs while adding new PluginRegistry features.

Per AGENTS.md §9: Both smoke tests and real agentic tests required.
"""

import threading
import unittest
from unittest import mock
from typing import Type, Optional

import praisonai.endpoints.registry as registry_module
from praisonai.endpoints.providers.base import BaseProvider, HealthResult, InvokeResult, ProviderInfo
from praisonai.endpoints.discovery import EndpointInfo


class MockProvider(BaseProvider):
    """Mock provider for testing."""

    provider_type = "mock"

    def __init__(self, base_url="http://localhost:8765", api_key=None, **kwargs):
        super().__init__(base_url=base_url, api_key=api_key)
        self.kwargs = kwargs

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(type="mock", name="mock", version="1.0", description="mock")

    def list_endpoints(self, tags=None):
        return []

    def describe_endpoint(self, name: str):
        return None

    def invoke(self, name, input_data=None, config=None, stream=False) -> InvokeResult:
        return InvokeResult(ok=True, data={})

    def health(self) -> HealthResult:
        return HealthResult(healthy=True)


class TestProviderRegistryBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility of ProviderRegistry refactor."""

    def setUp(self):
        """Reset registry state for each test."""
        # Reset the default registry
        registry_module._default_registry = None

    def test_provider_registry_smoke(self):
        """Smoke test: basic registry operations work."""
        from praisonai.endpoints.registry import ProviderRegistry
        
        registry = ProviderRegistry()
        self.assertIsNotNone(registry)
        
        # Should have expected methods from PluginRegistry inheritance
        self.assertTrue(hasattr(registry, 'register'))
        self.assertTrue(hasattr(registry, 'resolve'))
        self.assertTrue(hasattr(registry, 'list_names'))

    def test_backward_compat_instance_methods(self):
        """Test that old ProviderRegistry instance methods still work."""
        from praisonai.endpoints.registry import ProviderRegistry
        
        registry = ProviderRegistry()
        
        # Register a test provider
        registry.register("test", MockProvider)
        
        # Backward compatibility methods should work
        self.assertTrue(hasattr(registry, 'list_types'))
        self.assertTrue(hasattr(registry, 'get_class'))
        
        # list_types() should return provider types
        types = registry.list_types()
        self.assertIsInstance(types, list)
        self.assertIn("test", types)
        
        # get_class() should return provider class
        provider_class = registry.get_class("test")
        self.assertEqual(provider_class, MockProvider)
        
        # get_class() should return None for missing provider
        missing_class = registry.get_class("nonexistent")
        self.assertIsNone(missing_class)

    def test_module_level_functions_preserved(self):
        """Test that all module-level functions still work."""
        # These functions should exist and delegate to default registry
        functions_to_test = [
            'register_provider',
            'get_provider', 
            'list_provider_types',
            'get_provider_class'
        ]
        
        for func_name in functions_to_test:
            self.assertTrue(hasattr(registry_module, func_name),
                f"Missing backward compat function: {func_name}")

    def test_register_provider_module_function(self):
        """Test module-level register_provider function."""
        # Register via module function
        registry_module.register_provider("test_module", MockProvider)
        
        # Should be available via other module functions
        types = registry_module.list_provider_types()
        self.assertIn("test_module", types)
        
        provider_class = registry_module.get_provider_class("test_module")
        self.assertEqual(provider_class, MockProvider)

    def test_get_provider_module_function(self):
        """Test module-level get_provider function."""
        # Register a provider
        registry_module.register_provider("test_get", MockProvider)
        
        # Get provider instance via module function
        provider = registry_module.get_provider(
            "test_get",
            base_url="http://test:8080",
            api_key="secret123",
            extra_param="value"
        )
        
        self.assertIsInstance(provider, MockProvider)
        self.assertEqual(provider.base_url, "http://test:8080")
        self.assertEqual(provider.api_key, "secret123")
        self.assertEqual(provider.kwargs["extra_param"], "value")

    def test_get_provider_class_error_handling(self):
        """Test proper error handling in get_provider_class function."""
        # Test missing provider returns None
        result = registry_module.get_provider_class("definitely_missing")
        self.assertIsNone(result)
        
        # Test import error handling via lazy loader (not cached class)
        registry = registry_module.get_default_registry()
        registry._items.pop("failing_provider", None)
        registry._loaders["failing_provider"] = lambda: (_ for _ in ()).throw(ImportError("Mock import failure"))

        with self.assertRaises(ValueError):
            registry_module.get_provider_class("failing_provider")

    def test_default_registry_singleton_thread_safety(self):
        """Test that default registry singleton is thread-safe."""
        results = {}
        
        def get_registry_in_thread(thread_id):
            registry = registry_module.get_default_registry()
            results[thread_id] = id(registry)
        
        # Create multiple threads accessing default registry
        threads = []
        for i in range(10):
            thread = threading.Thread(target=get_registry_in_thread, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # All threads should get the same registry instance
        registry_ids = list(results.values())
        self.assertEqual(len(set(registry_ids)), 1, 
            "Multiple registry instances created - not thread-safe")

    def test_registry_get_method_error_handling(self):
        """Test error handling in ProviderRegistry.get() method."""
        from praisonai.endpoints.registry import ProviderRegistry
        
        registry = ProviderRegistry()
        
        # Missing provider should return None
        result = registry.get("missing_provider")
        self.assertIsNone(result)
        
        # Mock a provider whose lazy loader fails to import
        registry._items.pop("failing_provider", None)
        registry._loaders["failing_provider"] = lambda: (_ for _ in ()).throw(ImportError("Mock import failure"))

        with self.assertRaises(ValueError):
            registry.get("failing_provider")

    def test_builtin_providers_loaded(self):
        """Test that builtin providers are properly loaded."""
        from praisonai.endpoints.registry import get_default_registry
        
        registry = get_default_registry()
        available_types = registry.list_names()
        
        # Should have the expected builtin providers
        expected_builtins = ["recipe", "agents-api", "mcp", "tools-mcp", "a2a", "a2u"]
        
        for builtin in expected_builtins:
            self.assertIn(builtin, available_types,
                f"Missing builtin provider: {builtin}")

    def test_provider_instantiation_end_to_end(self):
        """Test complete provider instantiation workflow."""
        # Register a custom provider
        registry_module.register_provider("custom", MockProvider)
        
        # Get provider instance with various parameters
        provider = registry_module.get_provider(
            "custom",
            base_url="https://custom.api.com",
            api_key="sk-custom123",
            timeout=30,
            retries=3
        )
        
        # Verify provider was created correctly
        self.assertIsInstance(provider, MockProvider)
        self.assertEqual(provider.base_url, "https://custom.api.com") 
        self.assertEqual(provider.api_key, "sk-custom123")
        self.assertEqual(provider.kwargs["timeout"], 30)
        self.assertEqual(provider.kwargs["retries"], 3)

    def test_try_create_backward_compatibility(self):
        """Test backward compatibility of try_create pattern if it existed."""
        # This tests the pattern mentioned in the original request
        from praisonai.endpoints.registry import ProviderRegistry
        
        registry = ProviderRegistry()
        registry.register("test_create", MockProvider)
        
        # Test successful creation
        provider = registry.get("test_create", api_key="test123")
        self.assertIsNotNone(provider)
        self.assertEqual(provider.api_key, "test123")
        
        # Test failed creation (missing provider)
        provider = registry.get("nonexistent")
        self.assertIsNone(provider)


if __name__ == '__main__':
    unittest.main()