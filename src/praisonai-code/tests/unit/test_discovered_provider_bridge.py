"""Regression tests for issue #5607 — discovered custom/plugin providers must
reach model routing, credential resolution, and default/cloud-key checks, not
just appear in catalogue/auth listings.

These cover the gaps raised in PR review:

- ``provider_for_model`` must resolve an explicit ``myprovider/model`` to the
  discovered provider BEFORE bare-name fallbacks (so ``gptlike/…`` is not
  misattributed to OpenAI, ``geminity/…`` not to Gemini).
- a stored credential for a discovered provider must satisfy ``is_configured``.
- a discovered provider's ``<PROVIDER>_API_KEY`` must count as a cloud key.
- ``inject_credentials_into_env`` must export a discovered provider's key.
"""

import os

import pytest

from praisonaiagents.llm.adapters import add_provider_adapter, DefaultAdapter
from praisonai_code.llm import catalogue as cat
from praisonai_code.llm import credentials as creds
from praisonai_code.llm import env as llm_env


@pytest.fixture(autouse=True)
def _register_custom_providers():
    class GptLike(DefaultAdapter):
        pass

    class Geminity(DefaultAdapter):
        pass

    add_provider_adapter("gptlike5607", GptLike())
    add_provider_adapter("geminity5607", Geminity())
    yield


def _clear_api_keys():
    saved = {k: v for k, v in os.environ.items() if k.endswith("_API_KEY")}
    for k in saved:
        os.environ.pop(k, None)
    return saved


def test_provider_for_model_explicit_prefix_wins_over_bare_name():
    # A custom prefix that merely starts with a built-in name must not be
    # misattributed to the built-in provider.
    assert cat.provider_for_model("gptlike5607/model") == "gptlike5607"
    assert cat.provider_for_model("geminity5607/model") == "geminity5607"
    # Built-ins unchanged.
    assert cat.provider_for_model("gpt-4o") == "openai"
    assert cat.provider_for_model("gemini/gemini-1.5-flash") == "gemini"
    assert cat.provider_for_model("claude-3-5-sonnet") == "anthropic"


def test_env_vars_and_catalogue_include_discovered():
    assert cat.env_vars_for_provider("gptlike5607") == ("GPTLIKE5607_API_KEY",)
    all_vars = cat.provider_env_vars()
    assert "GPTLIKE5607_API_KEY" in all_vars
    assert "GEMINITY5607_API_KEY" in all_vars


def test_has_provider_credential_recognises_discovered_key():
    saved = _clear_api_keys()
    try:
        assert llm_env.has_provider_credential() is False
        os.environ["GPTLIKE5607_API_KEY"] = "sk-test"
        assert llm_env.has_provider_credential() is True
    finally:
        os.environ.pop("GPTLIKE5607_API_KEY", None)
        os.environ.update(saved)


def test_stored_providers_for_vars_maps_discovered():
    mapped = creds._stored_providers_for_vars(("GPTLIKE5607_API_KEY",))
    assert "gptlike5607" in mapped


def test_inject_credentials_exports_discovered_key(monkeypatch):
    saved = _clear_api_keys()

    class _Cred:
        provider = "gptlike5607"
        api_key = "sk-plugin-key"
        base_url = None
        model = None
        metadata = {}

        def is_oauth(self):
            return False

    class _Store:
        def list_providers(self):
            return ["gptlike5607"]

        def get_credential(self, provider):
            return _Cred() if provider == "gptlike5607" else None

    monkeypatch.setattr(creds, "CredentialStore", _Store)
    try:
        injected = creds.inject_credentials_into_env()
        assert injected is True
        assert os.environ.get("GPTLIKE5607_API_KEY") == "sk-plugin-key"
    finally:
        os.environ.pop("GPTLIKE5607_API_KEY", None)
        os.environ.update(saved)
