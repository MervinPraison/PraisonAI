"""Tests for issue #6228 — explicit ``ollama/`` models need no API key.

An explicit Ollama model is gated on the server being reachable, not on
``OLLAMA_HOST`` being set; the probe tolerates a slow first response; and the
error text for an explicit model does not claim auto-detection would kick in.
"""

import io
import json

import pytest
import typer

from praisonai_code.llm import credentials, local_detect


_ENV = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "GROQ_API_KEY", "COHERE_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_HOST",
    "OLLAMA_API_BASE", "OPENAI_BASE_URL", "MODEL_NAME", "OPENAI_MODEL_NAME",
    "PRAISONAI_LOCAL_ENDPOINTS",
)


@pytest.fixture
def clean_env(monkeypatch):
    for var in _ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(credentials, "inject_credentials_into_env", lambda: False)
    local_detect.reset_cache()
    yield monkeypatch
    local_detect.reset_cache()


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(seen, delay=0.0):
    def _urlopen(url, timeout):
        seen.append((url, timeout))
        if delay > timeout:
            raise TimeoutError("probe timed out")
        return _Resp(json.dumps({"models": [{"name": "llama3.2:latest"}]}).encode())
    return _urlopen


def _refuse(url, timeout):
    raise ConnectionRefusedError()


def test_explicit_ollama_configured_when_reachable(clean_env):
    seen = []
    clean_env.setattr(local_detect.urllib.request, "urlopen", _fake_urlopen(seen))
    assert credentials.is_configured("ollama/llama3.2") is True
    assert seen[0][0] == "http://127.0.0.1:11434/api/tags"


def test_explicit_ollama_honours_ollama_api_base(clean_env):
    seen = []
    clean_env.setenv("OLLAMA_API_BASE", "http://gpu-box:11434")
    clean_env.setattr(local_detect.urllib.request, "urlopen", _fake_urlopen(seen))
    assert credentials.is_configured("ollama_chat/llama3.2") is True
    assert seen[0][0] == "http://gpu-box:11434/api/tags"


def test_explicit_ollama_not_configured_when_unreachable(clean_env):
    clean_env.setattr(local_detect.urllib.request, "urlopen", _refuse)
    assert credentials.is_configured("ollama/llama3.2") is False


def test_unreachable_ollama_error_is_actionable(clean_env, capsys):
    clean_env.setattr(local_detect.urllib.request, "urlopen", _refuse)
    with pytest.raises(typer.Exit):
        credentials.ensure_configured_or_onboard(
            model="ollama/llama3.2", interactive=False
        )
    err = capsys.readouterr().err
    assert "Ollama isn't reachable at http://127.0.0.1:11434" in err
    assert "ollama serve" in err
    assert "API key" not in err


def test_explicit_ollama_passes_gate_when_reachable(clean_env):
    clean_env.setattr(local_detect.urllib.request, "urlopen", _fake_urlopen([]))
    assert credentials.ensure_configured_or_onboard(
        model="ollama/llama3.2", interactive=False
    ) == "ollama/llama3.2"


def test_probe_tolerates_slow_first_response(clean_env):
    """A ~0.4 s first /api/tags response must still be detected."""
    clean_env.setattr(
        local_detect.urllib.request, "urlopen", _fake_urlopen([], delay=0.4)
    )
    result = local_detect.detect_local_model(use_cache=False)
    assert result is not None
    assert result.model == "ollama/llama3.2:latest"


def test_explicit_cloud_model_error_omits_auto_detect_hint(clean_env, capsys):
    clean_env.setattr(credentials, "detect_local_endpoint", lambda: None)
    clean_env.setattr(credentials, "is_configured", lambda model=None: False)
    with pytest.raises(typer.Exit):
        credentials.ensure_configured_or_onboard(
            model="gpt-4o-mini", interactive=False
        )
    err = capsys.readouterr().err
    assert "for model gpt-4o-mini" in err
    assert "automatically" not in err


def test_keyless_no_model_error_mentions_auto_detect(clean_env, capsys):
    clean_env.setattr(credentials, "detect_local_endpoint", lambda: None)
    clean_env.setattr(credentials, "is_configured", lambda model=None: False)
    with pytest.raises(typer.Exit):
        credentials.ensure_configured_or_onboard(model=None, interactive=False)
    assert "automatically" in capsys.readouterr().err
