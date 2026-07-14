"""Tests for issue #3014 — catalogue-driven credential onboarding.

Onboarding must:

1. Drive provider selection from ``ModelCatalogue`` (not a hardcoded five) in
   both ``praisonai setup`` and ``praisonai auth login``, with a "custom"
   escape hatch.
2. Show a one-line "Get your key: <url>" hint for well-known providers before
   prompting for a masked key.
3. Fold active provider environment-variable keys (redacted, marked
   env-sourced) into ``auth list``/``auth status``.
"""

import os

import pytest

from praisonai_code.cli.features.setup.handler import SetupHandler
from praisonai_code.llm.catalogue import (
    ModelCatalogue,
    PROVIDER_KEY_URLS,
    key_url_for_provider,
)
from praisonai_code.cli.commands import auth as auth_cmd


_PROVIDER_KEY_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "COHERE_API_KEY",
    "OPENROUTER_API_KEY",
    "MISTRAL_API_KEY",
    "DEEPSEEK_API_KEY",
    "XAI_API_KEY",
    "TOGETHER_API_KEY",
    "PERPLEXITYAI_API_KEY",
)


@pytest.fixture
def clean_env(monkeypatch):
    for var in _PROVIDER_KEY_VARS + ("MODEL_NAME", "OPENAI_MODEL_NAME"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


# --- Catalogue provider enumeration + key URLs -----------------------------


def test_catalogue_lists_providers_beyond_the_hardcoded_five():
    providers = ModelCatalogue().list_providers()
    # Must include catalogue providers outside the old five.
    assert "groq" in providers
    assert "openai" in providers
    # Sorted + de-duplicated.
    assert providers == sorted(providers)
    assert len(providers) == len(set(providers))


def test_key_url_for_known_and_unknown_provider():
    assert key_url_for_provider("openai") == PROVIDER_KEY_URLS["openai"]
    assert key_url_for_provider("OpenAI") == PROVIDER_KEY_URLS["openai"]
    assert key_url_for_provider("groq") is not None
    assert key_url_for_provider("no-such-provider") is None
    assert key_url_for_provider("") is None


# --- Setup handler catalogue-driven picker ---------------------------------


def test_catalogue_provider_choices_includes_more_than_five_and_custom_last():
    menu = SetupHandler()._catalogue_provider_choices()
    # More than the old hardcoded five.
    assert len(menu) > 5
    pids = [entry[0] for entry in menu.values()]
    # OpenAI first, custom escape hatch last.
    assert pids[0] == "openai"
    assert pids[-1] == "custom"
    # A non-menu provider (e.g. groq) is now selectable.
    assert "groq" in pids
    # Every entry is (provider_id, env_key, default_model, name).
    for value in menu.values():
        assert len(value) == 4


def test_provider_setup_info_derives_env_key_for_catalogue_only_provider():
    defaults = SetupHandler()._provider_defaults()
    env_key, default_model, name = SetupHandler()._provider_setup_info(
        "mistral", defaults
    )
    assert env_key == "MISTRAL_API_KEY"
    assert name == "Mistral"


def test_provider_setup_info_env_key_matches_auth_for_perplexity():
    # setup must write the SAME env-var name auth (and the runtime) reads back.
    defaults = SetupHandler()._provider_defaults()
    env_key, _default_model, _name = SetupHandler()._provider_setup_info(
        "perplexity", defaults
    )
    assert env_key == "PERPLEXITYAI_API_KEY"
    assert env_key == auth_cmd._PROVIDER_ENV_KEYS["perplexity"]


def test_provider_setup_info_derives_default_model_for_catalogue_provider():
    # Catalogue providers that have models get a non-interactive default so
    # `praisonai setup --non-interactive --provider groq` no longer fails.
    defaults = SetupHandler()._provider_defaults()
    _env_key, default_model, _name = SetupHandler()._provider_setup_info(
        "groq", defaults
    )
    assert default_model is not None


def test_provider_menu_backcompat_shape_preserved():
    # Existing five-item numeric menu contract is unchanged.
    menu = SetupHandler()._provider_menu()
    assert set(menu) == {"1", "2", "3", "4", "5"}
    assert menu["1"][0] == "openai"
    assert menu["5"][0] == "custom"


def test_setup_key_url_hint_printed_for_known_provider():
    messages = []

    class _Out:
        class console:
            @staticmethod
            def print(*a, **k):
                messages.append(" ".join(str(x) for x in a))

    SetupHandler()._print_key_url_hint("openai", _Out())
    assert any("Get your key" in m and "openai" in m for m in messages)


def test_setup_key_url_hint_silent_for_unknown_provider():
    messages = []

    class _Out:
        class console:
            @staticmethod
            def print(*a, **k):
                messages.append(" ".join(str(x) for x in a))

    SetupHandler()._print_key_url_hint("totally-unknown", _Out())
    assert messages == []


# --- auth env-var visibility helpers ---------------------------------------


def test_env_credentials_reports_present_env_keys(clean_env):
    clean_env.setenv("GROQ_API_KEY", "gsk_" + "x" * 24)
    creds = auth_cmd._env_credentials()
    assert "groq" in creds
    env_var, value = creds["groq"]
    assert env_var == "GROQ_API_KEY"
    assert value.startswith("gsk_")


def test_env_credentials_empty_without_keys(clean_env):
    assert auth_cmd._env_credentials() == {}


def test_auth_key_url_hint_uses_print_info():
    calls = []

    class _Out:
        def print_info(self, msg):
            calls.append(msg)

    auth_cmd._print_key_url_hint("anthropic", _Out())
    assert calls
    assert "Get your key" in calls[0]
