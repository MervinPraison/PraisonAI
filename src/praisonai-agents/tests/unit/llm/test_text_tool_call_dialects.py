"""Text tool-call salvage for local-model dialects (issue #5864)."""
import json

from praisonaiagents.llm.adapters import _recover_json_tool_calls

TOOLS = [
    {"type": "function", "function": {"name": "web_search", "parameters": {}}},
    {"type": "function", "function": {"name": "get_weather", "parameters": {}}},
]


def _calls(text):
    out = _recover_json_tool_calls(text, TOOLS)
    return [(c["function"]["name"], json.loads(c["function"]["arguments"])) for c in out or []]


def test_react_next_line():
    text = ('Thought: I should look this up.\nAction: web_search\n'
            'Action Input: {"query": "praisonai gateway"}')
    assert _calls(text) == [("web_search", {"query": "praisonai gateway"})]


def test_react_same_line_and_nested_args():
    text = 'Action: web_search Action Input: {"query": "x", "opts": {"n": 3}}\nObservation:'
    assert _calls(text) == [("web_search", {"query": "x", "opts": {"n": 3}})]


def test_bracketed_tool_call_and_tool_request():
    text = ('[TOOL_CALL]{"name": "web_search", "arguments": {"query": "a"}}[/TOOL_CALL] then '
            '[TOOL_REQUEST]{"name": "get_weather", "arguments": {"city": "Paris"}}[END_TOOL_REQUEST]')
    assert _calls(text) == [("web_search", {"query": "a"}), ("get_weather", {"city": "Paris"})]


def test_llama_python_tag():
    text = '<|python_tag|>{"name": "get_weather", "parameters": {"city": "Paris"}}<|eom_id|>'
    assert _calls(text) == [("get_weather", {"city": "Paris"})]


def test_mixed_dialects_keep_emission_order():
    text = ('Action: get_weather\nAction Input: {"city": "Rome"}\n'
            '<tool_call>{"name": "web_search", "arguments": {"query": "b"}}</tool_call>')
    assert _calls(text) == [("get_weather", {"city": "Rome"}), ("web_search", {"query": "b"})]


def test_unadvertised_tool_is_never_invented():
    assert _calls('Action: delete_all\nAction Input: {}') == []
    assert _calls('<|python_tag|>{"name": "delete_all", "parameters": {}}') == []


def test_fenced_example_is_not_run():
    text = 'Example:\n```\nAction: web_search\nAction Input: {"query": "x"}\n```\nDone.'
    assert _calls(text) == []


def test_plain_prose_without_markers_is_untouched():
    assert _recover_json_tool_calls('The action was taken. {"a": 1}', TOOLS) is None


def test_react_non_json_input_is_ignored():
    assert _calls('Action: web_search\nAction Input: praisonai gateway') == []


def test_non_string_name_is_skipped_not_raised():
    text = ('<|python_tag|>{"name": ["get_weather"], "parameters": {}}\n'
            '[TOOL_CALL]{"name": {"x": 1}, "arguments": {}}[/TOOL_CALL]\n'
            '<tool_call>{"name": "web_search", "arguments": {"query": "ok"}}</tool_call>')
    assert _calls(text) == [("web_search", {"query": "ok"})]


def test_marker_inside_arguments_is_not_a_second_call():
    text = ('<tool_call>{"name": "web_search", "arguments": '
            '{"query": "Action: get_weather Action Input: {}"}}</tool_call>')
    assert _calls(text) == [("web_search", {"query": "Action: get_weather Action Input: {}"})]


def test_react_extra_whitespace_in_marker():
    text = 'Action: web_search Action  Input: {"query": "x"}'
    assert _calls(text) == [("web_search", {"query": "x"})]


def test_marker_inside_rejected_call_is_not_run():
    inner = '{"q": "Action: web_search Action Input: {}"}'
    for text in (
        '<tool_call>{"name": "not_advertised", "arguments": %s}</tool_call>' % inner,
        '[TOOL_CALL]{"name": ["web_search"], "arguments": %s}[/TOOL_CALL]' % inner,
        '<function=not_advertised>%s</function>' % inner,
        '<|python_tag|>{"name": "not_advertised", "parameters": %s}' % inner,
    ):
        assert _calls(text) == [], text
    # A valid call after a rejected one still runs.
    text = ('<tool_call>{"name": "nope", "arguments": %s}</tool_call>\n'
            'Action: get_weather\nAction Input: {"city": "Rome"}' % inner)
    assert _calls(text) == [("get_weather", {"city": "Rome"})]
