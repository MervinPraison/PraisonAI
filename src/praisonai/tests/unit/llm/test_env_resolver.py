"""
Unit tests for praisonai.llm.env.resolve_llm_endpoint().

Tests cover:
- Correct precedence order: OPENAI_BASE_URL > OPENAI_API_BASE > OLLAMA_API_BASE > default
- Model resolution: MODEL_NAME > OPENAI_MODEL_NAME > default
- API key resolution from OPENAI_API_KEY
- Default values when no env vars are set
- Frozen dataclass immutability
"""

import os
import pytest
from unittest.mock import patch

try:
    from praisonai.llm.env import resolve_llm_endpoint, LLMEndpoint, _DEFAULT_MODEL, _DEFAULT_BASE
except ImportError as e:
    pytest.skip(f"Could not import praisonai.llm.env: {e}", allow_module_level=True)


class TestResolveDefaults:
    """Tests for default values when no env vars are set."""

    def test_default_model(self):
        with patch.dict(os.environ, {}, clear=True):
            ep = resolve_llm_endpoint()
        assert ep.model == _DEFAULT_MODEL

    def test_default_base_url(self):
        with patch.dict(os.environ, {}, clear=True):
            ep = resolve_llm_endpoint()
        assert ep.base_url == _DEFAULT_BASE

    def test_default_api_key_is_none(self):
        with patch.dict(os.environ, {}, clear=True):
            ep = resolve_llm_endpoint()
        assert ep.api_key is None

    def test_custom_default_base(self):
        with patch.dict(os.environ, {}, clear=True):
            ep = resolve_llm_endpoint(default_base="https://custom.default.com/v1")
        assert ep.base_url == "https://custom.default.com/v1"


class TestBaseUrlPrecedence:
    """Tests for base URL precedence: OPENAI_BASE_URL > OPENAI_API_BASE > OLLAMA_API_BASE."""

    def test_openai_base_url_wins_over_api_base(self):
        env = {
            "OPENAI_BASE_URL": "https://base-url.com/v1",
            "OPENAI_API_BASE": "https://api-base.com/v1",
            "OLLAMA_API_BASE": "https://ollama.com",
        }
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
        assert ep.base_url == "https://base-url.com/v1"

    def test_openai_api_base_wins_over_ollama(self):
        env = {
            "OPENAI_API_BASE": "https://api-base.com/v1",
            "OLLAMA_API_BASE": "https://ollama.com",
        }
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
        assert ep.base_url == "https://api-base.com/v1"

    def test_ollama_api_base_used_as_last_fallback(self):
        env = {"OLLAMA_API_BASE": "http://localhost:11434"}
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
        assert ep.base_url == "http://localhost:11434"

    def test_empty_string_is_not_used(self):
        env = {"OPENAI_BASE_URL": "", "OPENAI_API_BASE": "https://api-base.com/v1"}
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
        assert ep.base_url == "https://api-base.com/v1"


class TestModelPrecedence:
    """Tests for model precedence: MODEL_NAME > OPENAI_MODEL_NAME > default."""

    def test_model_name_wins_over_openai_model_name(self):
        env = {"MODEL_NAME": "llama3", "OPENAI_MODEL_NAME": "gpt-4o"}
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
        assert ep.model == "llama3"

    def test_openai_model_name_fallback(self):
        env = {"OPENAI_MODEL_NAME": "gpt-4o"}
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
        assert ep.model == "gpt-4o"


class TestApiKey:
    """Tests for API key resolution."""

    def test_api_key_from_env(self):
        env = {"OPENAI_API_KEY": "sk-test-key"}
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
        assert ep.api_key == "sk-test-key"

    def test_api_key_none_when_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            ep = resolve_llm_endpoint()
        assert ep.api_key is None


class TestLLMEndpointDataclass:
    """Tests for LLMEndpoint dataclass properties."""

    def test_returns_llmendpoint_instance(self):
        ep = resolve_llm_endpoint()
        assert isinstance(ep, LLMEndpoint)

    def test_is_frozen(self):
        ep = resolve_llm_endpoint()
        with pytest.raises(AttributeError):
            ep.model = "new-model"  # type: ignore[misc]

    def test_has_expected_fields(self):
        ep = resolve_llm_endpoint()
        assert hasattr(ep, "model")
        assert hasattr(ep, "base_url")
        assert hasattr(ep, "api_key")


class TestProviderMapping:
    """Tests for provider-specific API key and base URL resolution."""

    def test_anthropic_model_uses_anthropic_key(self):
        env = {"ANTHROPIC_API_KEY": "sk-anthropic-test"}
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
            # Use direct function call to test provider mapping
            from praisonai.llm.env import _provider_from_model
            key_var, base_url = _provider_from_model("anthropic/claude-3-5-sonnet")
            assert key_var == "ANTHROPIC_API_KEY"
            assert base_url == "https://api.anthropic.com/v1"

    def test_anthropic_model_with_custom_env(self):
        env = {
            "MODEL_NAME": "anthropic/claude-3-5-sonnet",
            "ANTHROPIC_API_KEY": "sk-anthropic-test"
        }
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
            assert ep.model == "anthropic/claude-3-5-sonnet"
            assert ep.api_key == "sk-anthropic-test"
            assert ep.base_url == "https://api.anthropic.com/v1"

    def test_anthropic_model_no_fallback_to_openai(self):
        """Critical security test: Anthropic models should NOT fall back to OPENAI_API_KEY."""
        env = {
            "MODEL_NAME": "anthropic/claude-3-5-sonnet", 
            "OPENAI_API_KEY": "sk-openai-test"
            # ANTHROPIC_API_KEY intentionally missing
        }
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
            assert ep.model == "anthropic/claude-3-5-sonnet"
            assert ep.api_key is None  # Should NOT use OPENAI_API_KEY
            assert ep.base_url == "https://api.anthropic.com/v1"

    def test_groq_model_mapping(self):
        env = {
            "MODEL_NAME": "groq/llama-3.1-70b-versatile",
            "GROQ_API_KEY": "gsk-test-key"
        }
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
            assert ep.model == "groq/llama-3.1-70b-versatile"
            assert ep.api_key == "gsk-test-key"
            assert ep.base_url == "https://api.groq.com/openai/v1"

    def test_openai_model_uses_openai_key(self):
        """OpenAI models should use OPENAI_API_KEY normally."""
        env = {
            "MODEL_NAME": "gpt-4o",
            "OPENAI_API_KEY": "sk-openai-test"
        }
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
            assert ep.model == "gpt-4o"
            assert ep.api_key == "sk-openai-test"
            assert ep.base_url == "https://api.openai.com/v1"

    def test_ollama_model_mapping(self):
        env = {
            "MODEL_NAME": "ollama/llama3", 
            "OLLAMA_API_KEY": "ollama-test"
        }
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
            assert ep.model == "ollama/llama3"
            assert ep.api_key == "ollama-test"
            assert ep.base_url == "http://localhost:11434/v1"

    def test_google_model_mapping(self):
        env = {
            "MODEL_NAME": "google/gemini-pro",
            "GOOGLE_API_KEY": "google-test-key"
        }
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
            assert ep.model == "google/gemini-pro"
            assert ep.api_key == "google-test-key"
            assert ep.base_url == "https://generativelanguage.googleapis.com/v1beta"

    def test_all_providers_have_correct_base_urls(self):
        """Ensure all provider mappings have proper base URLs (not None)."""
        from praisonai.llm.env import _PROVIDER_MAP
        
        expected_urls = {
            "anthropic/": "https://api.anthropic.com/v1",
            "google/": "https://generativelanguage.googleapis.com/v1beta",
            "gemini/": "https://generativelanguage.googleapis.com/v1beta", 
            "groq/": "https://api.groq.com/openai/v1",
            "cohere/": "https://api.cohere.ai/v1",
            "openrouter/": "https://openrouter.ai/api/v1",
            "ollama/": "http://localhost:11434/v1",
        }
        
        for prefix, (key_var, base_url) in _PROVIDER_MAP.items():
            assert base_url is not None, f"Provider {prefix} has None base URL"
            assert base_url == expected_urls[prefix], f"Provider {prefix} has unexpected URL {base_url}"

    def test_provider_key_precedence_no_cross_contamination(self):
        """Ensure providers don't accidentally use other providers' keys.""" 
        env = {
            "MODEL_NAME": "anthropic/claude-3-5-sonnet",
            "GROQ_API_KEY": "gsk-groq-key",
            "GOOGLE_API_KEY": "google-key", 
            "OPENAI_API_KEY": "sk-openai-key"
            # ANTHROPIC_API_KEY intentionally missing
        }
        with patch.dict(os.environ, env, clear=True):
            ep = resolve_llm_endpoint()
            assert ep.model == "anthropic/claude-3-5-sonnet"
            # Should be None, not any other provider's key
            assert ep.api_key is None
