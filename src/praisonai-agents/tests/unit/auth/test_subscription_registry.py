"""Tests for subscription auth registry."""
import pytest
from praisonaiagents.auth.subscription.protocols import SubscriptionCredentials, AuthError
from praisonaiagents.auth.subscription.registry import (
    register_subscription_provider,
    list_subscription_providers, 
    resolve_subscription_credentials,
    _REGISTRY
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Clean the registry before and after each test."""
    original_registry = _REGISTRY.copy()
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()
    _REGISTRY.update(original_registry)


def test_register_and_resolve():
    """Test registering and resolving a provider."""
    class MockAuth:
        def resolve_credentials(self): 
            return SubscriptionCredentials(api_key="test-key", source="mock")
        def refresh(self): 
            return self.resolve_credentials()
        def headers_for(self, *_): 
            return {}

    register_subscription_provider("test-mock", lambda: MockAuth())
    assert "test-mock" in list_subscription_providers()
    
    creds = resolve_subscription_credentials("test-mock")
    assert creds.api_key == "test-key"
    assert creds.source == "mock"


def test_resolve_unknown_provider():
    """Test resolving an unknown provider raises AuthError."""
    with pytest.raises(AuthError) as exc_info:
        resolve_subscription_credentials("unknown-provider")
    
    assert "Unknown subscription provider 'unknown-provider'" in str(exc_info.value)