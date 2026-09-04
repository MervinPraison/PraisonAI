"""One tool result must produce one message, whichever response path built it.

`llm.py` carried FIVE inline copies of the tool-result formatter, and they had
drifted into three different behaviours:

    copy    error sentence              list-error   json.dumps guarded
    2950    "...inform the user."       yes          no
    3769    "...could not be completed" yes          no
    4990    "...inform the user."       NO           no
    5274    "...could not be completed" yes          no
    6789    "...could not be completed" yes          YES

So the same tool returning the same value produced a different message depending
on which internal branch happened to handle it -- and on one async branch a tool
returning [{"error": ...}] was JSON-dumped as data rather than surfaced as an
error at all.

`DefaultAdapter.format_tool_result_message` already declared this job and had
zero consumers. These tests pin the single behaviour all five now share.
"""

import json

import pytest

from praisonaiagents.llm.adapters import DefaultAdapter, OllamaAdapter

pytestmark = pytest.mark.unit


def fmt(result, tool_call_id="call_1"):
    return DefaultAdapter().format_tool_result_message("get_weather", result, tool_call_id)


def test_shape_is_the_openai_tool_message():
    msg = fmt({"temp": 21})
    assert msg["role"] == "tool"
    assert msg["tool_call_id"] == "call_1"
    assert json.loads(msg["content"]) == {"temp": 21}


def test_none_result():
    assert fmt(None)["content"] == "Function returned an empty output"


def test_dict_error_is_surfaced_as_an_error():
    content = fmt({"error": "boom"})["content"]
    assert content.startswith("Error: boom.")
    assert "could not be completed" in content


def test_list_error_is_surfaced_as_an_error():
    """One async branch dumped this as JSON instead of reporting the failure."""
    content = fmt([{"error": "boom"}])["content"]
    assert content.startswith("Error: boom.")
    assert "could not be completed" in content


def test_error_sentence_is_the_same_everywhere():
    """Two of the five copies used a shorter, different sentence."""
    assert fmt({"error": "x"})["content"] == fmt([{"error": "x"}])["content"]


@pytest.mark.parametrize("value", [[], "text", 3, 0, False, {"a": 1}, [1, 2]])
def test_ordinary_values_are_json(value):
    assert json.loads(fmt(value)["content"]) == value


def test_non_serializable_result_does_not_raise():
    """Four of the five copies raised TypeError here. Only the stream path guarded it.

    A tool returning a set, a datetime or any custom object crashed the whole
    turn on every path except streaming.
    """
    msg = fmt({"tags"})
    assert msg["role"] == "tool"
    assert isinstance(msg["content"], str) and msg["content"]


def test_missing_tool_call_id_gets_a_deterministic_one():
    assert DefaultAdapter().format_tool_result_message("get_weather", 1)["tool_call_id"]


def test_ollama_still_overrides_with_its_own_shape():
    """The Ollama variant must be untouched: it is the one real divergence."""
    msg = OllamaAdapter().format_tool_result_message("get_weather", {"t": 21}, "call_1")
    assert msg["role"] == "user"


def test_llm_delegates_to_the_adapter(monkeypatch):
    """_create_tool_message is now the single formatter for non-Ollama providers."""
    from praisonaiagents.llm.llm import LLM

    llm = LLM(model="gpt-4o")
    sentinel = {"role": "tool", "tool_call_id": "x", "content": "SENTINEL"}
    monkeypatch.setattr(llm._provider_adapter, "format_tool_result_message",
                        lambda *a, **kw: sentinel)
    assert llm._create_tool_message("f", {"a": 1}, "call_1", is_ollama=False) is sentinel
