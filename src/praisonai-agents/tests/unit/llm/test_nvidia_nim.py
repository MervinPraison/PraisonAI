"""NVIDIA NIM routing, credentials, tool_choice and Nemotron 3 reasoning (#5822)."""

import pytest

from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.model_providers import to_litellm_nvidia_nim
from praisonaiagents.thinking.effort import resolve_reasoning_params

SUPER = "nvidia_nim/nvidia/nemotron-3-super-120b-a12b"
TOOLS = [{"type": "function", "function": {"name": "get_weather", "parameters": {"type": "object", "properties": {}}}}]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("NVIDIA_NIM_API_KEY", "NVIDIA_API_KEY", "NVIDIA_NIM_API_BASE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-OPENAI-SECRET")


@pytest.mark.parametrize("model,expected", [
    ("nvidia/nemotron-3-super-120b-a12b", SUPER),
    ("nvidia/nemotron-super", SUPER),
    ("nvidia/Nemotron-Super", SUPER),
    ("nvidia/nemotron-nano", "nvidia_nim/nvidia/nemotron-nano-3-30b-a3b"),
    ("nvidia/nemotron-ultra", "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"),
    ("nvidia/meta/llama-3.3-70b-instruct", "nvidia_nim/meta/llama-3.3-70b-instruct"),
    ("nvidia/nvidia/nemotron-3-super-120b-a12b", SUPER),
    ("nvidia_nim/nvidia/foo", None),
    ("nemotron-super", None),
    ("nvidia/", None),
])
def test_to_litellm_nvidia_nim(model, expected):
    assert to_litellm_nvidia_nim(model) == expected


def test_llm_routes_nvidia_prefix_and_keeps_display_model(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")
    llm = LLM(model="nvidia/nemotron-super")
    assert llm._build_completion_params()["model"] == SUPER
    assert llm.model == "nvidia/nemotron-super"


def test_existing_nvidia_nim_prefix_unchanged(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nim-key")
    params = LLM(model=SUPER)._build_completion_params()
    assert params["model"] == SUPER
    assert params["api_key"] == "nim-key"


def test_key_precedence(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nim-key")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-key")
    assert LLM(model="nvidia/nemotron-super", api_key="explicit")._build_completion_params()["api_key"] == "explicit"
    assert LLM(model="nvidia/nemotron-super")._build_completion_params()["api_key"] == "nim-key"
    monkeypatch.delenv("NVIDIA_NIM_API_KEY")
    assert LLM(model="nvidia/nemotron-super")._build_completion_params()["api_key"] == "nvapi-key"


def test_openai_key_never_sent_to_nim(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-key")
    assert LLM(model=SUPER)._build_completion_params()["api_key"] == "nvapi-key"


def test_local_nim_needs_no_key():
    params = LLM(model="nvidia/nemotron-super", base_url="http://localhost:8000/v1")._build_completion_params()
    assert params["api_key"] == "not-used"
    assert params["base_url"] == "http://localhost:8000/v1"


def test_local_nim_via_env_base(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_API_BASE", "http://nim.local:8000/v1")
    assert LLM(model=SUPER)._build_completion_params()["api_key"] == "not-used"


def test_hosted_nim_without_key_raises():
    with pytest.raises(ValueError, match="NVIDIA_API_KEY"):
        LLM(model="nvidia/nemotron-super")._build_completion_params()


def test_non_nim_models_untouched():
    params = LLM(model="gpt-4o-mini")._build_completion_params()
    assert "api_key" not in params


def test_tool_choice_auto_on_nim(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-key")
    params = LLM(model="nvidia/nemotron-super")._build_completion_params(tools=TOOLS, stream=True)
    assert params["tool_choice"] == "auto"
    assert params["stream"] is True


def test_tool_choice_unchanged_for_unknown_non_nim_model():
    params = LLM(model="openai/some-unknown-model-xyz")._build_completion_params(tools=TOOLS)
    assert "tool_choice" not in params


@pytest.mark.parametrize("effort,expected", [
    ("off", {"enable_thinking": False}),
    ("minimal", {"enable_thinking": True, "low_effort": True}),
    ("low", {"enable_thinking": True, "low_effort": True}),
    ("medium", {"enable_thinking": True}),
    ("high", {"enable_thinking": True}),
])
def test_nemotron3_reasoning_switch(effort, expected):
    assert resolve_reasoning_params(effort, SUPER) == {"chat_template_kwargs": expected}
    assert resolve_reasoning_params(effort, "nvidia_nim/nvidia/nemotron-nano-3-30b-a3b") == {"chat_template_kwargs": expected}


def test_nemotron_reasoning_unset_or_other_routes_send_nothing():
    assert resolve_reasoning_params(None, SUPER) == {}
    assert resolve_reasoning_params("off", "ollama/nemotron-3-super") == {}
    assert resolve_reasoning_params("off", "nvidia_nim/meta/llama-3.3-70b-instruct") == {}
    assert resolve_reasoning_params("off", "gpt-4o") == {}


def test_reasoning_effort_reaches_nim_request(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-key")
    params = LLM(model="nvidia/nemotron-super", reasoning_effort="off")._build_completion_params()
    assert params["chat_template_kwargs"] == {"enable_thinking": False}


def test_user_chat_template_kwargs_wins(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-key")
    user = {"chat_template_kwargs": {"enable_thinking": True}}
    params = LLM(model="nvidia/nemotron-super", reasoning_effort="off")._build_completion_params(extra_body=user)
    assert "chat_template_kwargs" not in params
    assert params["extra_body"] == user
    params = LLM(model="nvidia/nemotron-super", reasoning_effort="off")._build_completion_params(
        chat_template_kwargs={"enable_thinking": True})
    assert params["chat_template_kwargs"] == {"enable_thinking": True}
