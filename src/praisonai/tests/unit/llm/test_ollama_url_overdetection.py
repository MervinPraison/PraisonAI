"""A base_url must not decide which model family is being addressed.

``LLM._is_ollama_provider`` treated any base_url containing "ollama" or ":11434"
as proof of an Ollama model. So pointing an OpenAI-compatible proxy at a local
port -- which the README itself recommends -- gave ``gpt-4o`` and
``claude-3-5-sonnet`` the Ollama adapter: tool results downgraded to
natural-language ``role:user`` turns, streaming-with-tools disabled, and
forced-tool prompts injected into a conversation that never needed them.

A URL says *where* the server is, not *what* it serves. It may only imply Ollama
for a model that could plausibly be served locally. Closed-weights families
(gpt-*, claude*, gemini-*) cannot be; open-weights ones (qwen, llama, gemma,
mistral, deepseek) can, and must keep working.

Constructed state only: no network, no server.
"""

import pytest

from praisonaiagents.llm.llm import LLM

LOCAL_URL = "http://localhost:11434/v1"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _llm(model, **kw):
    return LLM(model=model, **kw)


# --- the defect: hosted models must not be captured by a local URL -----------

@pytest.mark.parametrize(
    "model",
    [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-3.5-turbo",
        "o1-preview",
        "o3-mini",
        "chatgpt-4o-latest",
        "claude-3-5-sonnet-latest",
        "claude-sonnet-4-5",
        "gemini-1.5-flash",
        "openai/gpt-4o",
        "anthropic/claude-3-5-sonnet-latest",
    ],
)
def test_local_base_url_does_not_capture_hosted_models(model):
    """A closed-weights model keeps its own provider behind a local URL."""
    llm = _llm(model, base_url=LOCAL_URL)
    assert llm._is_ollama_provider() is False, (
        f"{model!r} behind {LOCAL_URL} was detected as Ollama; it would receive "
        "Ollama tool-call repairs that corrupt a well-formed conversation"
    )
    assert llm._detect_provider() != "ollama"


@pytest.mark.parametrize(
    "model",
    [
        "bedrock/anthropic.claude-3-5-sonnet",
        "us.anthropic.claude-3-5-sonnet",
        "vertex_ai/claude-3-5-sonnet",
        "openrouter/anthropic/claude-3-5-sonnet",
        "openrouter/openai/gpt-4o",
        "openrouter/google/gemini-1.5-flash",
    ],
)
def test_local_base_url_does_not_capture_nested_routed_hosted_models(model):
    """Nested and vendor-qualified hosted routes keep their provider too.

    ``bedrock/anthropic.claude-*`` and ``openrouter/openai/gpt-*`` name a
    hosted family further down the route than the first segment. A local URL
    must not reassign them to Ollama -- the family, not the route depth, is the
    discriminator, matching the substring fallback in ``_detect_provider``.
    """
    llm = _llm(model, base_url=LOCAL_URL)
    assert llm._is_ollama_provider() is False, (
        f"{model!r} behind {LOCAL_URL} was detected as Ollama despite naming a "
        "hosted family in a nested route"
    )
    assert llm._detect_provider() != "ollama"


@pytest.mark.parametrize("env_var", ["OPENAI_BASE_URL", "OPENAI_API_BASE"])
def test_env_base_url_does_not_capture_hosted_models(monkeypatch, env_var):
    """Same rule when the local URL arrives via the environment.

    This is the exact configuration the README recommends for local models, so
    it must not silently reshape an OpenAI conversation.
    """
    monkeypatch.setenv(env_var, LOCAL_URL)
    llm = _llm("gpt-4o")
    assert llm._is_ollama_provider() is False
    assert llm._detect_provider() == "openai"


def test_url_containing_the_word_ollama_does_not_capture_gpt():
    """The substring "ollama" in a hostname is not evidence about the model."""
    llm = _llm("gpt-4o", base_url="https://ollama.mycorp.example/v1")
    assert llm._is_ollama_provider() is False


def test_claude_behind_local_url_resolves_to_anthropic():
    """Regression guard: the Ollama check runs before the claude name check."""
    llm = _llm("claude-3-5-sonnet-latest", base_url=LOCAL_URL)
    assert llm._detect_provider() == "anthropic"


# --- what must keep working: real local models -------------------------------

@pytest.mark.parametrize(
    "model",
    [
        "qwen3:0.6b",
        "llama3.2",
        "gemma-2b",
        "mistral-7b",
        "deepseek-r1",
        "phi3",
        "openai/qwen3:0.6b",
    ],
)
def test_local_base_url_still_detects_open_weight_models(model):
    """Open-weights models behind a local URL are still Ollama.

    gemma/llama/mistral/deepseek are matched to hosted vendors by
    ``model_providers.resolve_provider``, but they are open weights and are
    routinely served by Ollama -- so the closed-weights test, not the general
    provider matcher, is what gates URL detection.
    """
    llm = _llm(model, base_url=LOCAL_URL)
    assert llm._is_ollama_provider() is True, (
        f"{model!r} behind {LOCAL_URL} lost Ollama detection; it would lose the "
        "tool-call repairs weak local models depend on"
    )


def test_explicit_ollama_prefix_needs_no_url():
    llm = _llm("ollama/llama3.2")
    assert llm._is_ollama_provider() is True
    assert llm._detect_provider() == "ollama"


def test_hosted_model_with_explicit_ollama_prefix_is_still_ollama():
    """An explicit ollama/ prefix is the user speaking; it always wins."""
    llm = _llm("ollama/gpt-oss")
    assert llm._is_ollama_provider() is True


def test_no_base_url_no_ollama():
    assert _llm("gpt-4o")._is_ollama_provider() is False


def test_model_is_none_is_safe():
    llm = _llm("gpt-4o", base_url=LOCAL_URL)
    llm.model = None
    assert llm._is_ollama_provider() is False
