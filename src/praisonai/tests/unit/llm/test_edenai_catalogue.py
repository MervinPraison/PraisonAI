"""Tests for Eden AI in the CLI provider catalogue and endpoint resolver.

One ``PROVIDER_ENV_CATALOGUE`` row is what makes ``praisonai auth login edenai``,
``praisonai setup --provider edenai`` and ``is_configured()`` work, and the
``env.py`` row is what stops an ``edenai/...`` model from resolving to
OpenAI's endpoint. Both are asserted here, along with the guarantee that adding
Eden AI did not disturb the ordered credential precedence the catalogue relies
on.

No network access and no Eden AI credentials are required.
"""

import os

import pytest

try:
    from praisonai_code.llm.catalogue import (
        PROVIDER_ENV_CATALOGUE,
        env_vars_for_provider,
        key_url_for_provider,
        provider_for_model,
    )
    from praisonai_code.llm.env import (
        default_model_for_available_provider,
        resolve_llm_endpoint,
    )
except ImportError as exc:  # pragma: no cover - matches the sibling env-resolver test
    pytest.skip(f"Could not import praisonai_code.llm: {exc}", allow_module_level=True)


# Every credential/endpoint variable the resolver consults.
_PROVIDER_ENV = (
    "EDENAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "GOOGLE_API_KEY", "GROQ_API_KEY", "COHERE_API_KEY", "OPENROUTER_API_KEY",
    "MISTRAL_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY", "TOGETHER_API_KEY",
    "TOGETHERAI_API_KEY", "PERPLEXITYAI_API_KEY", "FIREWORKS_API_KEY",
    "FIREWORKS_AI_API_KEY", "OLLAMA_HOST", "OPENAI_BASE_URL", "OPENAI_API_BASE",
    "OLLAMA_API_BASE", "MODEL_NAME", "OPENAI_MODEL_NAME",
)

EDEN_MODEL = "edenai/anthropic/claude-sonnet-4-5"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in _PROVIDER_ENV:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------- catalogue

def test_edenai_is_catalogued_with_its_own_key_variable():
    assert "edenai" in PROVIDER_ENV_CATALOGUE
    assert env_vars_for_provider("edenai") == ("EDENAI_API_KEY",)
    # A gateway prefix, so the vendor/model tail stays part of the model id.
    assert PROVIDER_ENV_CATALOGUE["edenai"][2] == "edenai/"


def test_edenai_has_an_onboarding_key_hint():
    """`praisonai setup` prints this before prompting for a masked key."""
    assert key_url_for_provider("edenai")


@pytest.mark.parametrize(
    "model",
    [
        "edenai/openai/gpt-4.1-mini",
        "edenai/anthropic/claude-sonnet-4-5",
        "edenai/google/gemini-2.5-flash",
        # An unknown vendor still resolves: no model catalogue is consulted.
        "edenai/acme/some-future-model",
    ],
)
def test_eden_models_map_to_the_edenai_provider(model):
    assert provider_for_model(model) == "edenai"


def test_eden_prefix_does_not_shadow_other_providers():
    assert provider_for_model("openrouter/openai/gpt-4o-mini") == "openrouter"
    assert provider_for_model("anthropic/claude-3-5-sonnet") == "anthropic"
    assert provider_for_model("gpt-4o-mini") == "openai"


# -------------------------------------------------------- endpoint resolver

def test_eden_model_resolves_to_the_edenai_endpoint(monkeypatch):
    """The regression this row exists for.

    Without a catalogue/`_PROVIDER_MAP` entry, an ``edenai/...`` model fell
    through to the OpenAI default, so the resolver handed back
    ``https://api.openai.com/v1`` paired with an Eden AI key.
    """
    monkeypatch.setenv("EDENAI_API_KEY", "eden-test-key")
    monkeypatch.setenv("MODEL_NAME", EDEN_MODEL)

    endpoint = resolve_llm_endpoint()

    assert endpoint.model == EDEN_MODEL
    assert endpoint.base_url == "https://api.edenai.run/v3"
    assert endpoint.api_key == "eden-test-key"


def test_eden_model_does_not_pick_up_an_openai_key(monkeypatch):
    """An Eden AI model must not be credentialed from OPENAI_API_KEY."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-openai-secret")
    monkeypatch.setenv("MODEL_NAME", EDEN_MODEL)

    endpoint = resolve_llm_endpoint()

    assert endpoint.base_url == "https://api.edenai.run/v3"
    assert endpoint.api_key != "sk-real-openai-secret"


def test_only_an_eden_key_infers_an_eden_default_model(monkeypatch):
    monkeypatch.setenv("EDENAI_API_KEY", "eden-test-key")
    assert default_model_for_available_provider().startswith("edenai/")


# ---------------------------------------------------- credential injection

def test_stored_edenai_credential_is_exported_to_the_environment(monkeypatch, tmp_path):
    """`praisonai auth login edenai` must reach the runtime.

    The runtime resolves ``EDENAI_API_KEY`` from the environment and cannot
    read the CLI credential store (that would invert the package tiering), so
    ``inject_credentials_into_env`` is the seam between the two.
    """
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    from praisonai_code.cli.configuration.credentials import CredentialStore
    from praisonai_code.llm.credentials import inject_credentials_into_env

    store = CredentialStore()
    store.store_credential("edenai", api_key="eden-stored-key")
    assert "edenai" in [p.lower() for p in store.list_providers()]

    assert inject_credentials_into_env() is True
    assert os.environ["EDENAI_API_KEY"] == "eden-stored-key"


# -------------------------------------------------------------- regression

def test_existing_provider_precedence_is_unchanged(monkeypatch):
    """Eden AI is appended, so it never outranks an already-configured provider."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("EDENAI_API_KEY", "eden-test-key")
    assert default_model_for_available_provider() == "gpt-4o-mini"


def test_direct_provider_endpoints_are_unchanged(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MODEL_NAME", "gpt-4o-mini")
    assert resolve_llm_endpoint().base_url == "https://api.openai.com/v1"

    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    monkeypatch.setenv("MODEL_NAME", "openrouter/openai/gpt-4o-mini")
    assert resolve_llm_endpoint().base_url == "https://openrouter.ai/api/v1"
