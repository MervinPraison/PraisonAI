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
