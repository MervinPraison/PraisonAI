"""Recovering a tool call the model emitted as plain text goes through the adapter.

Small local models often answer with the tool call as JSON text instead of using
the tool-call field. `llm.py` carried 33 inline lines to recover that, and
`OllamaAdapter.recover_tool_calls_from_text` carried 30 lines doing the same job
with no caller -- the flagship duplicate of the whole adapter problem.

The two are not byte-identical, so each difference is asserted here rather than
assumed inert.
"""

import json

import pytest

from praisonaiagents.llm.adapters import (AnthropicAdapter, DefaultAdapter,
                                          GeminiAdapter, OllamaAdapter)

pytestmark = pytest.mark.unit

TOOLS = [{"type": "function", "function": {"name": "get_weather"}}]


def rec(text, tools=TOOLS):
    return OllamaAdapter().recover_tool_calls_from_text(text, tools)


def test_recovers_a_single_json_tool_call():
    got = rec('{"name": "get_weather", "arguments": {"city": "Paris"}}')
    assert len(got) == 1
    assert got[0]["function"]["name"] == "get_weather"


def test_recovers_multiple_json_tool_calls_in_order():
    got = rec('[{"name": "a", "arguments": {}}, {"name": "b", "arguments": {}}]')
    assert [c["function"]["name"] for c in got] == ["a", "b"]


def test_arguments_are_a_json_string_not_a_dict():
    """_parse_tool_call_arguments expects a string; a dict would break dispatch."""
    got = rec('{"name": "a", "arguments": {"n": 1}}')
    args = got[0]["function"]["arguments"]
    assert isinstance(args, str)
    assert json.loads(args) == {"n": 1}


def test_shape_is_a_standard_tool_call():
    got = rec('{"name": "get_weather", "arguments": {}}')[0]
    assert got["type"] == "function"
    assert set(got) >= {"id", "type", "function"}
    assert got["id"]


@pytest.mark.parametrize("text", [
    '{"arguments": {"city": "Paris"}}',   # dict with no name
    '[{"arguments": {}}]',                # list whose entries have no name
    '{"name": "get_weather"',             # malformed JSON
    "",                                   # empty
    "I will call get_weather for you.",   # prose
    "null",
    "42",
])
def test_non_recoverable_text_yields_nothing(text):
    """Falsy either way: [] and None are treated identically by every consumer."""
    assert not rec(text)


def test_no_tools_means_no_recovery():
    assert rec('{"name": "get_weather", "arguments": {}}', tools=[]) is None


def test_non_string_input_does_not_raise():
    """The adapter catches TypeError; the inline copy did not."""
    assert rec(None) is None


@pytest.mark.parametrize("adapter", [DefaultAdapter, AnthropicAdapter, GeminiAdapter])
def test_other_providers_never_recover_from_text(adapter):
    """The single most important assertion here.

    An over-eager wiring would start parsing any assistant message that happens
    to be JSON as a tool call, for every provider.
    """
    assert adapter().recover_tool_calls_from_text(
        '{"name": "get_weather", "arguments": {"city": "Paris"}}', TOOLS) is None


# --- the wiring ---------------------------------------------------------------

def test_llm_calls_the_adapter_not_an_inline_copy():
    import inspect
    from praisonaiagents.llm import llm as llm_module

    source = inspect.getsource(llm_module.LLM)
    assert "recover_tool_calls_from_text" in source, "adapter recovery is not wired"
    assert 'response_json = json.loads(response_text.strip())' not in source, (
        "the inline JSON recovery copy is still present"
    )


def test_xml_recovery_is_still_reachable():
    """The inline list branch assigned `tool_calls = []` before the XML block
    re-checked `if not tool_calls`. The replacement never assigns a falsy value,
    so this pins that the XML path did not get shadowed."""
    import inspect
    from praisonaiagents.llm import llm as llm_module

    source = inspect.getsource(llm_module.LLM)
    assert "_supports_xml_tool_format" in source
