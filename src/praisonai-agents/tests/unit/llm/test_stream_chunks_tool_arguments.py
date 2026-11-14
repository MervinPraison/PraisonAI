"""process_stream_chunks must keep tool-call arguments from every delta.

OpenAI's own API sends a tool call's first delta with ``arguments: ""`` and
the JSON in later deltas, but many OpenAI-compatible servers (vLLM, Ollama,
Gemini's compatibility layer, proxies) send the whole call, arguments
included, in one delta. The accumulator started every call from ``""`` and
dropped the first delta's arguments, so the agent logged
``Failed to parse tool call arguments: Expecting value`` and the tool never
ran (and no tool row reached a UI).
"""
import json
import types

from praisonaiagents.llm.openai_client import (
    _extract_tool_call_name_and_args,
    process_stream_chunks,
)


def _chunk(tool_calls=None, content=None, finish=None):
    delta = types.SimpleNamespace(content=content, reasoning_content=None, tool_calls=tool_calls)
    choice = types.SimpleNamespace(delta=delta, finish_reason=finish, index=0)
    return types.SimpleNamespace(id="c", created=0, model="m", system_fingerprint=None,
                                 choices=[choice], usage=None)


def _tc(index, call_id=None, name=None, arguments=None):
    return types.SimpleNamespace(
        index=index, id=call_id, type="function" if call_id else None,
        function=types.SimpleNamespace(name=name, arguments=arguments))


def _calls(resp):
    out = []
    for tc in resp.choices[0].message.tool_calls or []:
        name, args, call_id, err = _extract_tool_call_name_and_args(tc)
        assert err is None, err
        out.append((call_id, name, args))
    return out


def test_arguments_in_the_first_delta_are_kept():
    args = json.dumps({"command": "python3 --version"})
    resp = process_stream_chunks([
        _chunk([_tc(0, "call_1", "terminal", args)]),
        _chunk(finish="tool_calls"),
    ])
    assert _calls(resp) == [("call_1", "terminal", {"command": "python3 --version"})]


def test_openai_style_split_arguments_still_accumulate():
    resp = process_stream_chunks([
        _chunk([_tc(0, "call_1", "terminal", "")]),
        _chunk([_tc(0, None, None, '{"comm')]),
        _chunk([_tc(0, None, None, 'and": "ls"}')]),
        _chunk(finish="tool_calls"),
    ])
    assert _calls(resp) == [("call_1", "terminal", {"command": "ls"})]


def test_parallel_calls_append_to_their_own_index():
    resp = process_stream_chunks([
        _chunk([_tc(0, "a", "f", '{"x":'), _tc(1, "b", "g", '{"y":')]),
        _chunk([_tc(0, None, None, " 1}")]),
        _chunk([_tc(1, None, None, " 2}")]),
        _chunk(finish="tool_calls"),
    ])
    assert _calls(resp) == [("a", "f", {"x": 1}), ("b", "g", {"y": 2})]
