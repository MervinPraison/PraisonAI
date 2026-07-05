"""Tests for issue #2679 — world-class first-run onboarding.

The setup wizard must:

1. Auto-detect a provider whose ``*_API_KEY`` is already in the environment and
   offer it as the pre-selected default (auth becomes a confirmation).
2. Validate an entered key (reusing the ``auth login`` format check) before
   persisting, re-prompting on failure.
3. Run a post-setup smoke test (``Agent.start(...)``) to leave the user with a
   verified working agent, skippable via ``--no-verify``.
"""

import os

import pytest

from praisonai_code.cli.features.setup.handler import SetupHandler


_PROVIDER_KEY_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "COHERE_API_KEY",
    "OPENROUTER_API_KEY",
)


@pytest.fixture
def clean_env(monkeypatch):
    for var in _PROVIDER_KEY_VARS + ("MODEL_NAME", "OPENAI_MODEL_NAME"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_detect_returns_none_without_credentials(clean_env):
    assert SetupHandler()._detect_provider_from_env() is None


def test_detect_anthropic_from_env(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-" + "x" * 24)
    detected = SetupHandler()._detect_provider_from_env()
    assert detected is not None
    provider_id, env_key, model, name = detected
    assert provider_id == "anthropic"
    assert env_key == "ANTHROPIC_API_KEY"
    assert "claude" in model.lower() or model.startswith("anthropic/")
    assert name == "Anthropic"


def test_detect_openai_from_env(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "sk-" + "x" * 24)
    detected = SetupHandler()._detect_provider_from_env()
    assert detected is not None
    provider_id, env_key, model, name = detected
    assert provider_id == "openai"
    assert env_key == "OPENAI_API_KEY"


def test_provider_menu_shape():
    menu = SetupHandler()._provider_menu()
    assert set(menu) == {"1", "2", "3", "4", "5"}
    # Each entry is (provider_id, env_key, default_model, provider_name).
    for value in menu.values():
        assert len(value) == 4
    assert menu["1"][0] == "openai"
    assert menu["5"][0] == "custom"


def test_provider_defaults_use_current_models():
    defaults = SetupHandler()._provider_defaults()
    # Dated models must be gone; current strong defaults in place.
    assert defaults["anthropic"][2] != "claude-3-5-sonnet-latest"
    assert "claude" in defaults["anthropic"][2].lower()
    assert defaults["google"][2] != "gemini-1.5-flash"


def test_smoke_test_skipped_without_model():
    calls = []

    class _Out:
        class console:
            @staticmethod
            def print(*a, **k):
                calls.append(("print", a))

        def print_success(self, *a, **k):
            calls.append(("success", a))

        def print_warning(self, *a, **k):
            calls.append(("warning", a))

    # No model → smoke test is a no-op (no output at all).
    SetupHandler()._run_smoke_test(None, {}, _Out())
    assert calls == []


def test_smoke_test_reports_failure_without_aborting(clean_env, monkeypatch):
    """A failing agent must warn but never raise (config already persisted)."""
    messages = []

    class _Out:
        class console:
            @staticmethod
            def print(*a, **k):
                messages.append(str(a))

        def print_success(self, *a, **k):
            messages.append(("success",) + a)

        def print_warning(self, *a, **k):
            messages.append(("warning",) + a)

    import sys
    import types

    fake_mod = types.ModuleType("praisonaiagents")

    class _BoomAgent:
        def __init__(self, *a, **k):
            pass

        def start(self, *a, **k):
            raise RuntimeError("boom")

    fake_mod.Agent = _BoomAgent
    monkeypatch.setitem(sys.modules, "praisonaiagents", fake_mod)

    # Should not raise.
    SetupHandler()._run_smoke_test("openai/gpt-4o-mini", {}, _Out())
    assert any("warning" == m[0] for m in messages if isinstance(m, tuple))
