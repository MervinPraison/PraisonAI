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
        # gemini/ routes to GEMINI_API_KEY in the resolver.
        assert _provider_key_vars_for_model("gemini/gemini-1.5-flash") == ("GEMINI_API_KEY",)

    def test_google(self):
        # google/ routes to GOOGLE_API_KEY in the resolver (must match _PROVIDER_MAP).
        assert _provider_key_vars_for_model("google/gemini-1.5-flash") == ("GOOGLE_API_KEY",)

    def test_groq(self):
        assert _provider_key_vars_for_model("groq/llama-3.3-70b-versatile") == ("GROQ_API_KEY",)

    def test_openai(self):
        assert _provider_key_vars_for_model("gpt-4o-mini") == ("OPENAI_API_KEY",)

    def test_openai_o1_reasoning(self):
        assert _provider_key_vars_for_model("o1-mini") == ("OPENAI_API_KEY",)

    def test_openai_o3_reasoning(self):
        assert _provider_key_vars_for_model("o3-mini") == ("OPENAI_API_KEY",)

    def test_openai_o4_reasoning(self):
        assert _provider_key_vars_for_model("o4-mini") == ("OPENAI_API_KEY",)

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
        # Isolate the credential store so the clean-env case is deterministic:
        # no env vars AND an empty store must report not configured.
        with patch.dict(os.environ, {}, clear=True), \
                patch("praisonai.llm.credentials.CredentialStore") as MockStore:
            instance = MockStore.return_value
            instance.list_providers.return_value = []
            instance.get_credential.return_value = None
            assert is_configured() is False


class TestIsConfiguredStoredCredentials:
    """No env vars, but a stored non-OpenAI credential exists.

    When no model is passed, the inferred default is OpenAI (env-only), but the
    gate must still defer to the resolver so a stored credential for a different
    provider satisfies it (regression for the gate/resolver disagreement)."""

    def test_stored_anthropic_only_no_model_is_configured(self):
        from praisonai.cli.configuration.credentials import ProviderCredential

        with patch.dict(os.environ, {}, clear=True), \
                patch("praisonai.llm.credentials.CredentialStore") as MockStore:
            instance = MockStore.return_value
            instance.list_providers.return_value = ["anthropic"]
            instance.get_credential.return_value = ProviderCredential(
                provider="anthropic", api_key="sk-stored-a"
            )
            assert is_configured() is True

    def test_explicit_openai_model_with_stored_anthropic_only_not_configured(self):
        from praisonai.cli.configuration.credentials import ProviderCredential

        with patch.dict(os.environ, {}, clear=True), \
                patch("praisonai.llm.credentials.CredentialStore") as MockStore:
            instance = MockStore.return_value
            instance.list_providers.return_value = ["anthropic"]
            instance.get_credential.return_value = ProviderCredential(
                provider="anthropic", api_key="sk-stored-a"
            )
            # Explicit OpenAI model must stay strictly gated to OpenAI.
            assert is_configured("gpt-4o-mini") is False


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

    def test_gemini_model_requires_gemini_key(self):
        # gemini/ routes to GEMINI_API_KEY in the resolver, so GEMINI_API_KEY
        # satisfies the gate.
        with patch.dict(os.environ, {"GEMINI_API_KEY": "g"}, clear=True), \
                patch("praisonai.llm.credentials.CredentialStore") as MockStore:
            MockStore.return_value.list_providers.return_value = []
            assert is_configured("gemini/gemini-1.5-flash") is True

    def test_gemini_model_with_only_google_key_is_not_configured(self):
        # A google/ key does not satisfy a gemini/ model: the resolver reads
        # GEMINI_API_KEY for that prefix and would get no key at run time.
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "g"}, clear=True), \
                patch("praisonai.llm.credentials.CredentialStore") as MockStore:
            MockStore.return_value.list_providers.return_value = []
            assert is_configured("gemini/gemini-1.5-flash") is False

    def test_google_model_requires_google_key(self):
        # google/ routes to GOOGLE_API_KEY in the resolver; matching gate.
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "g"}, clear=True), \
                patch("praisonai.llm.credentials.CredentialStore") as MockStore:
            MockStore.return_value.list_providers.return_value = []
            assert is_configured("google/gemini-1.5-flash") is True

    def test_google_model_with_only_gemini_key_is_not_configured(self):
        # GEMINI_API_KEY alone must not satisfy a google/ model, because the
        # resolver reads GOOGLE_API_KEY and would get no key at run time.
        with patch.dict(os.environ, {"GEMINI_API_KEY": "g"}, clear=True), \
                patch("praisonai.llm.credentials.CredentialStore") as MockStore:
            MockStore.return_value.list_providers.return_value = []
            assert is_configured("google/gemini-1.5-flash") is False
