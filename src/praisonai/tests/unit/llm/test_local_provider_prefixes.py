"""Local-server route prefixes must select an adapter that knows they are local.

litellm resolves `ollama_chat/`, `lm_studio/`, `vllm/` and `hosted_vllm/`, but
`LLM._detect_provider` recognised only the bare `ollama/` prefix, so every other
local route fell through to "openai" and got `DefaultAdapter` with
`max_tool_repairs=0` -- no tool-call repair at all, for exactly the small local
models that need it most.

`ollama_chat/` is the sharpest case: it is litellm's *recommended* prefix for
Ollama tool calling, and it was the one form of Ollama the SDK did not detect.

Constructed state only: no network, no server.
"""

import pytest

from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.adapters import (
    DefaultAdapter,
    LocalOpenAIAdapter,
    OllamaAdapter,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


# --- ollama_chat/ is Ollama ---------------------------------------------------

@pytest.mark.parametrize("model", ["ollama_chat/llama3.2", "ollama_chat/qwen3:0.6b"])
def test_ollama_chat_prefix_is_ollama(model):
    """litellm's recommended Ollama prefix must resolve to Ollama."""
    llm = LLM(model=model)
    assert llm._detect_provider() == "ollama"
    assert isinstance(llm._provider_adapter, OllamaAdapter)
    assert llm.max_tool_repairs == 2


def test_ollama_chat_matches_ollama_prefix_behaviour():
    """The two Ollama spellings must not disagree."""
    chat = LLM(model="ollama_chat/llama3.2")
    plain = LLM(model="ollama/llama3.2")
    assert chat._detect_provider() == plain._detect_provider()
    assert type(chat._provider_adapter) is type(plain._provider_adapter)
    assert chat.max_tool_repairs == plain.max_tool_repairs


# --- OpenAI-compatible local servers -----------------------------------------

@pytest.mark.parametrize(
    "model",
    [
        "lm_studio/qwen2.5-7b-instruct",
        "vllm/meta-llama/Llama-3.1-8B-Instruct",
        "hosted_vllm/Qwen2.5-7B",
    ],
)
def test_local_openai_compatible_prefixes_get_repairs(model):
    """A local OpenAI-compatible server gets tool-call repair, not zero."""
    llm = LLM(model=model)
    assert llm._detect_provider() == "local"
    assert isinstance(llm._provider_adapter, LocalOpenAIAdapter)
    assert llm.max_tool_repairs == 2


@pytest.mark.parametrize(
    "model",
    [
        "lm_studio/qwen2.5-7b-instruct",
        "vllm/meta-llama/Llama-3.1-8B-Instruct",
    ],
)
def test_local_openai_compatible_keeps_openai_message_shape(model):
    """These servers speak real OpenAI, so tool results stay role:tool.

    This is what separates them from Ollama, whose adapter rewrites a tool
    result into a natural-language role:user turn. Applying that here would
    corrupt a conversation with a server that handles the standard protocol
    correctly.
    """
    llm = LLM(model=model)
    msg = llm._provider_adapter.format_tool_result_message("get_weather", {"c": 21}, "call_1")
    assert msg["role"] == "tool"
    assert msg["tool_call_id"] == "call_1"


def test_local_adapter_does_not_force_tool_usage():
    """Repairs are a safety net; forced-tool prompting is not applied blind.

    `max_tool_repairs` only fires on a malformed tool call, so it is safe for a
    strong model. `force_tool_usage` injects prompts into every conversation,
    and vLLM commonly serves large, capable models -- so it is deliberately not
    part of the local default.
    """
    settings = LocalOpenAIAdapter().get_default_settings()
    assert settings.get("max_tool_repairs") == 2
    assert "force_tool_usage" not in settings


def test_local_adapter_allows_streaming_with_tools():
    """Unlike Ollama, these servers stream tool calls correctly."""
    assert LocalOpenAIAdapter().supports_streaming_with_tools() is True


# --- what must not change -----------------------------------------------------

@pytest.mark.parametrize(
    "model, expected",
    [
        ("gpt-4o", "openai"),
        ("openai/gpt-4o", "openai"),
        ("claude-3-5-sonnet-latest", "anthropic"),
        ("anthropic/claude-3-5-sonnet-latest", "anthropic"),
        ("gemini/gemini-1.5-flash", "gemini"),
        ("groq/llama-3.3-70b-versatile", "openai"),
    ],
)
def test_existing_providers_unchanged(model, expected):
    assert LLM(model=model)._detect_provider() == expected


def test_huggingface_is_not_treated_as_local():
    """`huggingface/` is the hosted Inference API, not a local server."""
    llm = LLM(model="huggingface/meta-llama/Llama-3.1-8B-Instruct")
    assert llm._detect_provider() != "local"
    assert isinstance(llm._provider_adapter, DefaultAdapter)
    assert not isinstance(llm._provider_adapter, LocalOpenAIAdapter)
    assert llm.max_tool_repairs == 0


def test_openai_still_has_no_repairs():
    """The repair default must not leak onto hosted OpenAI."""
    assert LLM(model="gpt-4o").max_tool_repairs == 0


def test_explicit_max_tool_repairs_wins():
    """A user-set value is never overridden by a provider default."""
    assert LLM(model="lm_studio/qwen", max_tool_repairs=5).max_tool_repairs == 5
    assert LLM(model="ollama_chat/llama3.2", max_tool_repairs=0).max_tool_repairs == 0


# --- repair-response reconstruction (Greptile P1) -----------------------------

@pytest.mark.parametrize(
    "model",
    [
        "lm_studio/qwen2.5-7b-instruct",
        "vllm/meta-llama/Llama-3.1-8B-Instruct",
        "hosted_vllm/Qwen2.5-7B",
        "llamacpp/qwen2.5",
    ],
)
def test_local_openai_provider_flag(model):
    """Local OpenAI-compatible routes report as local for text reconstruction."""
    assert LLM(model=model)._is_local_openai_provider() is True


@pytest.mark.parametrize(
    "model",
    ["gpt-4o", "ollama/llama3.2", "ollama_chat/llama3.2", "claude-3-5-sonnet-latest"],
)
def test_non_local_providers_are_not_local_openai(model):
    """Hosted OpenAI, Ollama and Anthropic must not be flagged as local OpenAI."""
    assert LLM(model=model)._is_local_openai_provider() is False


def test_huggingface_is_not_local_openai():
    """`huggingface/` is the hosted Inference API, not a local server."""
    assert LLM(model="huggingface/meta-llama/Llama-3.1-8B-Instruct")._is_local_openai_provider() is False
