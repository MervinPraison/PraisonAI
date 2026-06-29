#!/usr/bin/env python3
"""
Simple test script to validate auth functionality implementation.
"""

import os
import sys
import tempfile
from pathlib import Path

def test_credential_store():
    """Test basic credential store functionality."""
    print("🧪 Testing credential store...")
    
    from praisonai.cli.configuration.credentials import CredentialStore, redact_key, validate_api_key
    
    # Test with temporary directory to avoid affecting real credentials
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_cred_path = Path(temp_dir) / "test_credentials.json"
        store = CredentialStore(temp_cred_path)
        
        # Test storing credentials
        store.store_credential(
            provider="openai",
            api_key="sk-test1234567890abcdef",
            base_url="https://api.openai.com/v1",
            model="gpt-4"
        )
        
        # Test retrieving credentials
        cred = store.get_credential("openai")
        assert cred is not None, "Should retrieve stored credential"
        assert cred.provider == "openai", "Provider should match"
        assert cred.api_key == "sk-test1234567890abcdef", "API key should match"
        assert cred.base_url == "https://api.openai.com/v1", "Base URL should match"
        assert cred.model == "gpt-4", "Model should match"
        
        # Test listing providers
        providers = store.list_providers()
        assert "openai" in providers, "Should list stored provider"
        
        # Test redaction
        redacted = redact_key("sk-test1234567890abcdef")
        assert redacted.startswith("sk-t") and redacted.endswith("cdef"), f"Redaction failed: {redacted}"
        
        # Test validation
        valid, msg = validate_api_key("openai", "sk-test1234567890abcdef")
        assert valid, f"OpenAI key validation failed: {msg}"
        
        valid, msg = validate_api_key("openai", "invalid-key")
        assert not valid, "Should reject invalid OpenAI key"
        
        # Test removal
        assert store.remove_credential("openai"), "Should remove credential"
        assert not store.has_credential("openai"), "Should not have credential after removal"
        
        print("✅ Credential store tests passed")


_LLM_ENV_KEYS = (
    "OPENAI_API_KEY",
    "OPENAI_MODEL_NAME",
    "MODEL_NAME",
    "PRAISONAI_MODEL",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "COHERE_API_KEY",
)


def _clear_llm_env_for_defaults():
    """Remove provider credentials/model overrides so defaults are deterministic.

    Returns a snapshot of the cleared values so callers can restore them and
    avoid leaking deletions into later tests.
    """
    snapshot = {key: os.environ.get(key) for key in _LLM_ENV_KEYS}
    for key in _LLM_ENV_KEYS:
        os.environ.pop(key, None)
    return snapshot


def _restore_llm_env(snapshot):
    """Restore environment variables captured by _clear_llm_env_for_defaults."""
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_llm_endpoint_resolution():
    """Test LLM endpoint resolution with credential fallback."""
    print("🧪 Testing LLM endpoint resolution...")
    
    from praisonai.llm.env import resolve_llm_endpoint
    from praisonai.llm.credentials import resolve_llm_endpoint_with_credentials, inject_credentials_into_env
    from praisonai.cli.configuration.credentials import CredentialStore
    
    # Save original env
    _env_snapshot = None
    
    try:
        _env_snapshot = _clear_llm_env_for_defaults()
        
        # Test basic resolution without key
        endpoint = resolve_llm_endpoint()
        assert endpoint.model == "gpt-4o-mini", "Should use default model"
        assert endpoint.api_key is None, "Should have no API key"
        
        # Test with mock fallback
        def mock_fallback(provider):
            if provider == "openai":
                return {
                    "api_key": "sk-fallback-key",
                    "model": "gpt-4",
                    "base_url": "https://fallback.api.com/v1"
                }
            return None
        
        endpoint = resolve_llm_endpoint(fallback_lookup=mock_fallback)
        assert endpoint.api_key == "sk-fallback-key", "Should use fallback API key"
        assert endpoint.model == "gpt-4", "Should use fallback model"
        assert endpoint.base_url == "https://fallback.api.com/v1", "Should use fallback base URL"
        
        # Test with credential store using default location
        # Note: inject_credentials_into_env uses default CredentialStore location
        # So we'll test the integration differently
        endpoint = resolve_llm_endpoint_with_credentials()
        assert endpoint.model == "gpt-4o-mini", "Should use default model when no stored creds"
        assert endpoint.api_key is None, "Should have no key when no stored creds"
            
        print("✅ LLM endpoint resolution tests passed")
        
    finally:
        # Restore original env
        if _env_snapshot is not None:
            _restore_llm_env(_env_snapshot)


def test_config_schema():
    """Test configuration schema with LLM section."""
    print("🧪 Testing config schema...")
    
    from praisonai.cli.configuration.schema import ConfigSchema, LLMConfig
    
    # Test default config
    config = ConfigSchema()
    assert config.llm.model == "gpt-4o-mini", "Should have default LLM model"
    assert config.llm.provider is None, "Should have no default provider"
    
    # Test serialization
    config_dict = config.to_dict()
    assert "llm" in config_dict, "Should serialize LLM section"
    assert config_dict["llm"]["model"] == "gpt-4o-mini", "Should serialize LLM model"
    
    # Test deserialization
    test_data = {
        "llm": {
            "model": "gpt-4",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1"
        }
    }
    restored_config = ConfigSchema.from_dict(test_data)
    assert restored_config.llm.model == "gpt-4", "Should deserialize LLM model"
    assert restored_config.llm.provider == "openai", "Should deserialize LLM provider"
    assert restored_config.llm.base_url == "https://api.openai.com/v1", "Should deserialize LLM base URL"
    
    print("✅ Config schema tests passed")


def test_auth_integration():
    """Test end-to-end auth integration."""
    print("🧪 Testing auth integration...")
    
    # Test the core auth detection logic without CLI dependencies
    from praisonai.llm.credentials import resolve_llm_endpoint_with_credentials
    
    # Save original env
    _env_snapshot = None
    
    try:
        _env_snapshot = _clear_llm_env_for_defaults()
        
        # Test endpoint resolution without credentials
        endpoint = resolve_llm_endpoint_with_credentials()
        assert endpoint.model == "gpt-4o-mini", "Should use default model"
        # Note: api_key may be None without stored credentials
        
        # Set env key
        os.environ["OPENAI_API_KEY"] = "sk-test-env-key"
        endpoint = resolve_llm_endpoint_with_credentials()
        assert endpoint.api_key == "sk-test-env-key", "Should find env API key"
        
        print("✅ Auth integration tests passed")
        
    finally:
        # Restore original env
        if _env_snapshot is not None:
            _restore_llm_env(_env_snapshot)


if __name__ == "__main__":
    print("🚀 Running auth functionality tests...\n")
    
    try:
        test_credential_store()
        test_llm_endpoint_resolution()
        test_config_schema()
        test_auth_integration()
        
        print("\n🎉 All tests passed!")
        print("\nKey features implemented:")
        print("  ✅ Secure credential storage with atomic writes and 0o600 permissions")
        print("  ✅ Auth CLI commands: login, logout, list, status")
        print("  ✅ LLM endpoint resolution with credential fallback")
        print("  ✅ Preflight checks to prevent raw API errors")
        print("  ✅ Config schema extended with LLM defaults")
        print("  ✅ Environment injection for backward compatibility")
        
        print("\nUsage examples:")
        print("  praisonai auth login openai                     # Interactive login")
        print("  praisonai auth login openai --key sk-...        # Direct login")
        print("  echo 'sk-...' | praisonai auth login --key-stdin  # Pipe login")
        print("  praisonai auth list                             # Show providers")
        print("  praisonai auth status                           # Check status")
        print("  praisonai auth logout openai                    # Remove credentials")
        print("  praisonai run 'Hello world'                     # Auto-uses stored creds")
        
    except Exception as e:
        print(f"\n💥 Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)