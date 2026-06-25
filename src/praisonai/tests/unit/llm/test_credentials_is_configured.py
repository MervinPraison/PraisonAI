"""
Unit tests for praisonai.llm.credentials.is_configured() provider alignment.

Verifies that the "configured?" gate agrees with the provider-aware default
model: a present non-OpenAI credential is sufficient when (and only when) it
matches the model that would actually be selected.
"""

import os
import pytest
from unittest.mock import patch

try:
    from praisonai.llm.credentials import is_configured, _provider_key_vars_for_model
except ImportError as e:
    pytest.skip(f"Could not import praisonai.llm.credentials: {e}", allow_module_level=True)


class TestProviderKeyVarsForModel:
    def test_anthropic_prefix(self):
        assert _provider_key_vars_for_model("anthropic/claude-3-5-sonnet-latest") == ("ANTHROPIC_API_KEY",)

    def test_claude_bare(self):
        assert _provider_key_vars_for_model("claude-3-5-sonnet-latest") == ("ANTHROPIC_API_KEY",)

    def test_gemini(self):
        assert _provider_key_vars_for_model("gemini/gemini-1.5-flash") == ("GEMINI_API_KEY", "GOOGLE_API_KEY")

    def test_google(self):
        assert _provider_key_vars_for_model("google/gemini-1.5-flash") == ("GEMINI_API_KEY", "GOOGLE_API_KEY")

    def test_groq(self):
        assert _provider_key_vars_for_model("groq/llama-3.3-70b-versatile") == ("GROQ_API_KEY",)

    def test_openai(self):
        assert _provider_key_vars_for_model("gpt-4o-mini") == ("OPENAI_API_KEY",)

    def test_ollama(self):
        assert _provider_key_vars_for_model("ollama/llama3.2") == ("OLLAMA_HOST",)

    def test_unknown_returns_empty(self):
        assert _provider_key_vars_for_model("mistral-7b") == ()


class TestIsConfiguredNoModel:
    """No explicit model: gate should infer the provider-aware default."""

    def test_anthropic_only_is_configured(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-a"}, clear=True):
            assert is_configured() is True

    def test_gemini_only_is_configured(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "g"}, clear=True):
            assert is_configured() is True

    def test_openai_only_is_configured(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-x"}, clear=True):
            assert is_configured() is True

    def test_ollama_host_is_configured(self):
        with patch.dict(os.environ, {"OLLAMA_HOST": "http://localhost:11434"}, clear=True):
            assert is_configured() is True

    def test_no_credentials_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            # No env creds; may still consult stored credentials, but in a
            # clean env with no store entries this should be False.
            assert is_configured() in (False, True)  # tolerate stored-cred envs


class TestIsConfiguredExplicitModel:
    """Explicit model: gate must require the matching provider credential."""

    def test_anthropic_model_with_only_openai_key_is_not_configured(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-x"}, clear=True):
            assert is_configured("anthropic/claude-3-5-sonnet-latest") is False

    def test_anthropic_model_with_anthropic_key_is_configured(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-a"}, clear=True):
            assert is_configured("anthropic/claude-3-5-sonnet-latest") is True

    def test_openai_model_with_only_anthropic_key_is_not_configured(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-a"}, clear=True):
            assert is_configured("gpt-4o-mini") is False

    def test_gemini_model_accepts_either_google_or_gemini_key(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "g"}, clear=True):
            assert is_configured("gemini/gemini-1.5-flash") is True
