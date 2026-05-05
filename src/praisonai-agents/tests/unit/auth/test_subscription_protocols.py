"""Tests for subscription auth protocols."""
import pytest
from praisonaiagents.auth.subscription.protocols import (
    SubscriptionCredentials,
    SubscriptionAuthProtocol,
    AuthError
)


def test_credentials_dataclass_defaults():
    """Test SubscriptionCredentials dataclass defaults."""
    c = SubscriptionCredentials(api_key="test-key")
    assert c.api_key == "test-key"
    assert c.base_url == ""
    assert c.headers == {}
    assert c.auth_scheme == "bearer"
    assert c.expires_at_ms is None
    assert c.source == ""


def test_protocol_runtime_check():
    """Test that classes implementing the protocol are recognized."""
    class MockAuth:
        def resolve_credentials(self): 
            return SubscriptionCredentials(api_key="test")
        def refresh(self): 
            return SubscriptionCredentials(api_key="refreshed")
        def headers_for(self, base_url, model): 
            return {"x-test": "header"}

    assert isinstance(MockAuth(), SubscriptionAuthProtocol)


def test_auth_error():
    """Test AuthError exception."""
    with pytest.raises(AuthError) as exc_info:
        raise AuthError("test error")
    assert str(exc_info.value) == "test error"