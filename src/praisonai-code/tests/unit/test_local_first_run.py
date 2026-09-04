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
        "PRAISONAI_LOCAL_ENDPOINTS",
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
        local_detect, "_probe_ollama_tags", lambda host: "ollama/llama3.2:latest"
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
        return "ollama/mymodel"

    monkeypatch.setattr(local_detect, "_probe_ollama_tags", _probe)
    result = local_detect.detect_local_model(use_cache=False)
    assert seen["host"] == "http://localhost:1234"
    assert result.base_url == "http://localhost:1234/v1"


def test_probe_uses_root_ollama_tags_when_base_url_ends_in_v1(clean_env, monkeypatch):
    """A base URL ending in /v1 must probe the root /api/tags, not /v1/api/tags."""
    clean_env.setenv("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")
    urls = []

    def _fake_get_json(url):
        urls.append(url)
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.2:latest"}]}
        return None

    monkeypatch.setattr(local_detect, "_get_json", _fake_get_json)
    result = local_detect.detect_local_model(use_cache=False)
    assert result is not None
    assert result.model == "ollama/llama3.2:latest"
    assert "http://127.0.0.1:11434/api/tags" in urls
    assert "http://127.0.0.1:11434/v1/api/tags" not in urls


def test_probe_falls_back_to_openai_v1_models(clean_env, monkeypatch):
    """A generic OpenAI-compatible server (only /v1/models) must be detected."""
    clean_env.setenv("OPENAI_BASE_URL", "http://localhost:1234")

    def _fake_get_json(url):
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        return None  # /api/tags unreachable

    monkeypatch.setattr(local_detect, "_get_json", _fake_get_json)
    result = local_detect.detect_local_model(use_cache=False)
    assert result is not None
    assert result.model == "openai/local-model"
    assert result.base_url == "http://localhost:1234/v1"


def test_cache_is_keyed_by_endpoint(clean_env, monkeypatch):
    """A changed endpoint must not be served the previous endpoint's result."""
    def _probe(host):
        # Positive only for the second endpoint.
        return "ollama/m" if "5678" in host else None

    monkeypatch.setattr(local_detect, "_probe_ollama_tags", _probe)

    clean_env.setenv("OPENAI_BASE_URL", "http://localhost:1234")
    assert local_detect.detect_local_model() is None  # cached negative for :1234

    clean_env.setenv("OPENAI_BASE_URL", "http://localhost:5678")
    result = local_detect.detect_local_model()  # must re-probe the new endpoint
    assert result is not None
    assert result.model == "ollama/m"


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
    first_pass = calls["n"]  # one probe per default candidate
    assert first_pass >= 1
    assert local_detect.detect_local_model() is None
    assert calls["n"] == first_pass  # second call served from cache, no re-probe


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


def test_default_candidates_include_common_local_runtimes(clean_env):
    """Default probe list must cover Ollama, LM Studio, vLLM, Jan, llama.cpp."""
    hosts = local_detect._candidate_hosts()
    assert hosts[0] == "http://127.0.0.1:11434"  # Ollama stays first
    for port in ("1234", "8000", "1337", "8080"):
        assert any(port in h for h in hosts)


def test_detect_probes_candidates_until_first_reachable(clean_env, monkeypatch):
    """First reachable candidate wins and probing short-circuits."""
    probed = []

    def _probe(host):
        probed.append(host)
        return "openai/lmstudio-model" if "1234" in host else None

    monkeypatch.setattr(local_detect, "_probe_ollama_tags", _probe)
    result = local_detect.detect_local_model(use_cache=False)
    assert result is not None
    assert result.model == "openai/lmstudio-model"
    assert result.base_url == "http://127.0.0.1:1234/v1"
    # Ollama probed first, LM Studio second, then short-circuit (no vLLM etc.).
    assert probed == ["http://127.0.0.1:11434", "http://127.0.0.1:1234"]


def test_openai_base_url_skips_candidate_list(clean_env, monkeypatch):
    """An explicit override is probed alone; the default list is not consulted."""
    probed = []

    def _probe(host):
        probed.append(host)
        return "ollama/m"

    clean_env.setenv("OPENAI_BASE_URL", "http://localhost:9999")
    monkeypatch.setattr(local_detect, "_probe_ollama_tags", _probe)
    result = local_detect.detect_local_model(use_cache=False)
    assert result is not None
    assert probed == ["http://localhost:9999"]


def test_env_override_replaces_candidate_list(clean_env, monkeypatch):
    """PRAISONAI_LOCAL_ENDPOINTS replaces the built-in list."""
    probed = []

    def _probe(host):
        probed.append(host)
        return "openai/m" if "4321" in host else None

    clean_env.setenv(
        "PRAISONAI_LOCAL_ENDPOINTS", "127.0.0.1:2222, http://127.0.0.1:4321"
    )
    monkeypatch.setattr(local_detect, "_probe_ollama_tags", _probe)
    result = local_detect.detect_local_model(use_cache=False)
    assert result is not None
    assert probed == ["http://127.0.0.1:2222", "http://127.0.0.1:4321"]


def test_path_prefixed_endpoint_preserves_path_and_skips_api_tags(
    clean_env, monkeypatch
):
    """A runtime mounted under a path is probed at <path>/v1/models only.

    The explicit URL path must be preserved in both the probe URL and the
    returned base URL, and the Ollama-native /api/tags root probe must be
    skipped so the path is never rewritten.
    """
    clean_env.setenv("PRAISONAI_LOCAL_ENDPOINTS", "http://127.0.0.1:8000/openai")
    urls = []

    def _fake_get_json(url):
        urls.append(url)
        if url.endswith("/openai/v1/models"):
            return {"data": [{"id": "prefixed-model"}]}
        return None

    monkeypatch.setattr(local_detect, "_get_json", _fake_get_json)
    result = local_detect.detect_local_model(use_cache=False)
    assert result is not None
    assert result.model == "openai/prefixed-model"
    assert result.base_url == "http://127.0.0.1:8000/openai/v1"
    assert "http://127.0.0.1:8000/openai/v1/models" in urls
    # The Ollama-native /api/tags root probe must not fire for a path prefix.
    assert not any(u.endswith("/api/tags") for u in urls)


def test_env_override_empty_disables_probing(clean_env, monkeypatch):
    """An empty PRAISONAI_LOCAL_ENDPOINTS disables probing entirely."""
    def _boom(host):
        raise AssertionError("probing must not happen when disabled")

    clean_env.setenv("PRAISONAI_LOCAL_ENDPOINTS", "")
    monkeypatch.setattr(local_detect, "_probe_ollama_tags", _boom)
    assert local_detect.detect_local_model(use_cache=False) is None


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
