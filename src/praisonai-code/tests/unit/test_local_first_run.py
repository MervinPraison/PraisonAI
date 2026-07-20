"""Tests for issue #3200 — keyless, local-first first run.

When no cloud provider key is configured but a local OpenAI-compatible endpoint
(e.g. Ollama) is reachable, the CLI must use it as the zero-config default so
``praisonai run "..."`` just works before any auth. When nothing is reachable,
non-TTY behaviour must still fail fast with the existing guidance.
"""

import os

import pytest

from praisonai_code.llm import local_detect
from praisonai_code.llm.env import has_provider_credential


_PROVIDER_KEY_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "COHERE_API_KEY",
    "OPENROUTER_API_KEY",
    "OLLAMA_HOST",
)


@pytest.fixture
def clean_env(monkeypatch):
    for var in _PROVIDER_KEY_VARS + (
        "MODEL_NAME", "OPENAI_MODEL_NAME", "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    local_detect.reset_cache()
    yield monkeypatch
    local_detect.reset_cache()


def test_has_provider_credential_false_when_clean(clean_env):
    assert has_provider_credential() is False


def test_has_provider_credential_true_with_openai(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "sk-test")
    assert has_provider_credential() is True


def test_has_provider_credential_ignores_ollama_host(clean_env):
    """A local host is not a *cloud* key; it must not satisfy the cloud gate."""
    clean_env.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    assert has_provider_credential() is False


def test_detect_local_model_none_when_unreachable(clean_env, monkeypatch):
    monkeypatch.setattr(local_detect, "_probe_ollama_tags", lambda host: None)
    assert local_detect.detect_local_model(use_cache=False) is None


def test_detect_local_model_returns_ollama_model(clean_env, monkeypatch):
    monkeypatch.setattr(
        local_detect, "_probe_ollama_tags", lambda host: "llama3.2:latest"
    )
    result = local_detect.detect_local_model(use_cache=False)
    assert result is not None
    assert result.model == "ollama/llama3.2:latest"
    assert result.base_url.endswith("/v1")


def test_detect_honours_openai_base_url(clean_env, monkeypatch):
    clean_env.setenv("OPENAI_BASE_URL", "http://localhost:1234")
    seen = {}

    def _probe(host):
        seen["host"] = host
        return "mymodel"

    monkeypatch.setattr(local_detect, "_probe_ollama_tags", _probe)
    result = local_detect.detect_local_model(use_cache=False)
    assert seen["host"] == "http://localhost:1234"
    assert result.base_url == "http://localhost:1234/v1"


def test_detect_honours_ollama_host_without_scheme(clean_env, monkeypatch):
    clean_env.setenv("OLLAMA_HOST", "127.0.0.1:11434")
    seen = {}

    def _probe(host):
        seen["host"] = host
        return "m"

    monkeypatch.setattr(local_detect, "_probe_ollama_tags", _probe)
    local_detect.detect_local_model(use_cache=False)
    assert seen["host"].startswith("http://")


def test_negative_probe_is_cached(clean_env, monkeypatch):
    calls = {"n": 0}

    def _probe(host):
        calls["n"] += 1
        return None

    monkeypatch.setattr(local_detect, "_probe_ollama_tags", _probe)
    assert local_detect.detect_local_model() is None
    assert local_detect.detect_local_model() is None
    assert calls["n"] == 1  # second call served from cache


def test_resolver_falls_back_to_local_when_no_cloud_key(clean_env, monkeypatch):
    """resolve_default_model must return the detected local model keylessly."""
    from praisonai_code.cli.configuration import model_resolver

    monkeypatch.setattr(model_resolver, "get_recent_model", lambda: None)
    monkeypatch.setattr(
        local_detect,
        "detect_local_model",
        lambda *a, **k: local_detect.LocalModel(
            model="ollama/llama3.2", base_url="http://127.0.0.1:11434/v1"
        ),
    )

    resolved = model_resolver.resolve_default_model(
        None, persist=False, notify=False
    )
    assert resolved == "ollama/llama3.2"


def test_resolver_prefers_cloud_key_over_local(clean_env, monkeypatch):
    """A present cloud key must win; local detection is only a fallback."""
    from praisonai_code.cli.configuration import model_resolver

    monkeypatch.setattr(model_resolver, "get_recent_model", lambda: None)
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-test")

    def _boom(*a, **k):  # local detection must not even be consulted
        raise AssertionError("local detection consulted despite cloud key")

    monkeypatch.setattr(local_detect, "detect_local_model", _boom)

    resolved = model_resolver.resolve_default_model(
        None, persist=False, notify=False
    )
    assert "claude" in resolved.lower() or resolved.startswith("anthropic/")
