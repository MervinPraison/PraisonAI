"""A streaming tool call that SUCCEEDS but returns a non-JSON-serializable
value must not be reported to the model as an execution error.

The non-streaming sync/async loops in ``openai_client.py`` guard JSON
serialization separately from tool execution, so a tool returning a
``datetime`` (or ``set``, ``bytes``, DataFrame, custom object) falls into the
``except (TypeError, ValueError)`` branch and is stringified. The streaming
loop, ``chat_completion_with_tools_stream``, previously wrapped execution *and*
serialization in one ``try`` with only a generic ``except Exception`` -- so the
same successful tool call was mislabelled ``"Error executing function: ..."``.

This test drives the streaming loop with a tool that succeeds and returns a
``datetime`` and asserts the tool result carried to the model contains the
serialized value, not an error string.
"""
import json
import types
from datetime import datetime

from praisonaiagents.llm.openai_client import OpenAIClient
import praisonaiagents.llm.openai_client as oc


class _Fn:
    def __init__(self, name, args):
        self.name = name
        self.arguments = json.dumps(args)


class _ToolCall:
    def __init__(self, id, name, args):
        self.id = id
        self.type = "function"
        self.function = _Fn(name, args)


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.role = "assistant"
        self.content = content
        self.tool_calls = tool_calls


class _FinalResp:
    def __init__(self, msg):
        self.choices = [types.SimpleNamespace(message=msg, finish_reason="tool_calls")]


class _Stream:
    def __iter__(self):
        return iter(())


class _Completions:
    def create(self, **kwargs):
        return _Stream()


def test_streaming_non_serializable_success_is_not_reported_as_error(monkeypatch):
    client = OpenAIClient(api_key="sk-not-a-real-key")

    tool_call = _ToolCall("c1", "get_time", {})
    scripted = iter([
        _FinalResp(_Msg(tool_calls=[tool_call])),
        _FinalResp(_Msg(content="done", tool_calls=None)),
    ])

    fake_sync = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=_Completions())
    )
    monkeypatch.setattr(type(client), "sync_client",
                        property(lambda self: fake_sync))
    monkeypatch.setattr(oc, "process_stream_chunks",
                        lambda chunks: next(scripted))

    def execute_tool_fn(name, arguments, **kwargs):
        # Tool SUCCEEDS and returns a non-JSON-serializable value.
        return {"created_at": datetime(2024, 1, 1, 12, 0, 0)}

    messages = [{"role": "user", "content": "what time is it"}]
    list(client.chat_completion_with_tools_stream(
        messages=messages,
        model="gpt-4o-mini",
        tools=[lambda: None],
        execute_tool_fn=execute_tool_fn,
        verbose=False,
        max_iterations=2,
    ))

    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs, "no tool result message was appended for the model"
    content = tool_msgs[-1]["content"]
    assert not content.startswith("Error executing function"), (
        f"successful tool wrongly reported as an error: {content!r}"
    )
    # Parity with the sync/async fallback: stringified into {"result": "..."}.
    payload = json.loads(content)
    assert "result" in payload
    assert "2024" in payload["result"] and "created_at" in payload["result"]


def test_streaming_tool_execution_failure_still_reported_as_error(monkeypatch):
    """A tool that genuinely raises must still surface an execution error --
    the split try/except must not swallow real failures."""
    client = OpenAIClient(api_key="sk-not-a-real-key")

    tool_call = _ToolCall("c1", "boom", {})
    scripted = iter([
        _FinalResp(_Msg(tool_calls=[tool_call])),
        _FinalResp(_Msg(content="done", tool_calls=None)),
    ])
    fake_sync = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=_Completions())
    )
    monkeypatch.setattr(type(client), "sync_client",
                        property(lambda self: fake_sync))
    monkeypatch.setattr(oc, "process_stream_chunks",
                        lambda chunks: next(scripted))

    def execute_tool_fn(name, arguments, **kwargs):
        raise RuntimeError("kaboom")

    messages = [{"role": "user", "content": "explode"}]
    list(client.chat_completion_with_tools_stream(
        messages=messages,
        model="gpt-4o-mini",
        tools=[lambda: None],
        execute_tool_fn=execute_tool_fn,
        verbose=False,
        max_iterations=2,
    ))

    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs, "no tool result message was appended for the model"
    content = tool_msgs[-1]["content"]
    payload = json.loads(content)
    assert "error" in payload
    assert "kaboom" in payload["error"]
