"""The streaming chat path must fire the ``tool_call`` display callback.

Regression coverage for Issue #4716. The non-streaming path fires
``execute_sync_callback('tool_call', ...)`` from the OpenAI client after every
tool run; the streaming path executed its accumulated tool calls inline and
never told anyone, so streaming UIs (the desktop) saw no tool activity.
"""

import types

import pytest

import praisonaiagents.main as main_module
from praisonaiagents import Agent
from praisonaiagents.llm.openai_client import OpenAIClient
from praisonaiagents.main import register_display_callback


@pytest.fixture
def tool_call_events():
    """Register a ``tool_call`` callback for the test and restore the old one after."""
    events = []

    def on_tool_call(**kwargs):
        events.append(kwargs)

    with main_module._callbacks_lock:
        previous = main_module.sync_display_callbacks.get('tool_call')
    register_display_callback('tool_call', on_tool_call)
    try:
        yield events
    finally:
        with main_module._callbacks_lock:
            if previous is None:
                main_module.sync_display_callbacks.pop('tool_call', None)
            else:
                main_module.sync_display_callbacks['tool_call'] = previous


# --- fake streamed transport ------------------------------------------------

def _chunk(content=None, tool_calls=None, finish_reason=None):
    delta = types.SimpleNamespace(content=content, tool_calls=tool_calls)
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(delta=delta, finish_reason=finish_reason, index=0)]
    )


def _tool_call_delta(index, call_id, name, arguments):
    return types.SimpleNamespace(
        index=index,
        id=call_id,
        type="function",
        function=types.SimpleNamespace(name=name, arguments=arguments),
    )


class _StreamRecorder:
    """Scripted ``chat.completions.create``: each call returns the next stream."""

    def __init__(self, streams):
        self.streams = list(streams)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        i = len(self.requests) - 1
        if i >= len(self.streams):
            return iter([_chunk(content="fallback", finish_reason="stop")])
        return iter(self.streams[i])


def _streaming_agent(tool, streams):
    agent = Agent(name="A", instructions="x", llm="gpt-4o-mini", tools=[tool])
    rec = _StreamRecorder(streams)
    client = OpenAIClient(api_key="sk-not-a-real-key")
    client._sync_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=rec),
        beta=types.SimpleNamespace(chat=types.SimpleNamespace(completions=rec)),
        responses=None,
    )
    agent._Agent__openai_client = client
    agent._unified_dispatcher = None
    return agent, rec


def _tool_round_then_answer(name, arguments_json):
    """First stream requests tool ``name``; second stream is the answer."""
    return [
        [
            _chunk(tool_calls=[_tool_call_delta(0, "call_1", name, "")]),
            _chunk(tool_calls=[_tool_call_delta(0, None, None, arguments_json)]),
            _chunk(finish_reason="tool_calls"),
        ],
        [
            _chunk(content="The answer "),
            _chunk(content="is 42."),
            _chunk(finish_reason="stop"),
        ],
    ]


# --- OpenAI streaming path (chat_mixin) ------------------------------------

def test_stream_fires_tool_call_callback_once_per_tool(tool_call_events):
    calls = []

    def f(x: int) -> int:
        """Double a number."""
        calls.append(x)
        return x * 2

    agent, rec = _streaming_agent(f, _tool_round_then_answer("f", '{"x": 21}'))

    text = "".join(agent.start("double 21", stream=True))

    assert calls == [21], "the tool itself must still run exactly once"
    assert text == "The answer is 42."
    assert len(rec.requests) == 2, "tool round then follow-up answer"

    assert len(tool_call_events) == 1, tool_call_events
    event = tool_call_events[0]
    assert event["tool_name"] == "f"
    assert event["tool_input"] == {"x": 21}
    assert "42" in event["tool_output"]
    assert event["success"] is True
    assert isinstance(event["elapsed_time"], float)
    assert event["message"] == "Calling function: f"


def test_stream_fires_callback_for_each_parallel_tool_call(tool_call_events):
    def f(x: int) -> int:
        """Double a number."""
        return x * 2

    def g(y: str) -> str:
        """Shout a word."""
        return y.upper()

    streams = [
        [
            _chunk(tool_calls=[_tool_call_delta(0, "call_1", "f", '{"x": 1}')]),
            _chunk(tool_calls=[_tool_call_delta(1, "call_2", "g", '{"y": "hi"}')]),
            _chunk(finish_reason="tool_calls"),
        ],
        [_chunk(content="done"), _chunk(finish_reason="stop")],
    ]
    agent = Agent(name="A", instructions="x", llm="gpt-4o-mini", tools=[f, g])
    rec = _StreamRecorder(streams)
    client = OpenAIClient(api_key="sk-not-a-real-key")
    client._sync_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=rec),
        beta=types.SimpleNamespace(chat=types.SimpleNamespace(completions=rec)),
        responses=None,
    )
    agent._Agent__openai_client = client
    agent._unified_dispatcher = None

    assert "".join(agent.start("go", stream=True)) == "done"

    assert [(e["tool_name"], e["tool_input"]) for e in tool_call_events] == [
        ("f", {"x": 1}),
        ("g", {"y": "hi"}),
    ]


def test_stream_survives_a_raising_tool_call_callback():
    """The callback is best-effort: its exception must never break the stream."""
    events = []

    def exploding(**kwargs):
        events.append(kwargs)
        raise RuntimeError("UI is gone")

    with main_module._callbacks_lock:
        previous = main_module.sync_display_callbacks.get('tool_call')
    register_display_callback('tool_call', exploding)
    try:
        def f(x: int) -> int:
            """Double a number."""
            return x * 2

        agent, rec = _streaming_agent(f, _tool_round_then_answer("f", '{"x": 21}'))
        text = "".join(agent.start("double 21", stream=True))
    finally:
        with main_module._callbacks_lock:
            if previous is None:
                main_module.sync_display_callbacks.pop('tool_call', None)
            else:
                main_module.sync_display_callbacks['tool_call'] = previous

    assert len(events) == 1 and events[0]["tool_name"] == "f"
    assert text == "The answer is 42."
    assert len(rec.requests) == 2, "the follow-up answer still happened"
    # The callback failure must not be mistaken for a tool failure either:
    # the real tool result, not the callback's error, reaches the model.
    tool_turns = [m for m in agent.chat_history if m.get("role") == "tool"]
    assert len(tool_turns) == 1
    assert tool_turns[0]["content"] == "42"
    assert "UI is gone" not in tool_turns[0]["content"]
    followup_tool_turns = [m for m in rec.requests[1]["messages"] if m.get("role") == "tool"]
    assert [m["content"] for m in followup_tool_turns] == ["42"]


def test_notify_tool_call_reports_error_result_as_failure(tool_call_events):
    """A durable run returns a raising tool as ``{"error": ...}`` instead of
    re-raising, so the inline success branch would otherwise mislabel it.
    ``_notify_tool_call`` must downgrade an error-shaped result to
    ``success=False`` (Issue #4735 review)."""
    from praisonaiagents.agent.chat_mixin import ChatMixin

    ChatMixin._notify_tool_call(
        "f",
        {"x": 21},
        {"error": "boom"},
        elapsed_time=0.01,
        success=True,
    )

    assert len(tool_call_events) == 1, tool_call_events
    event = tool_call_events[0]
    assert event["tool_name"] == "f"
    assert event["success"] is False


# --- custom-LLM streaming path (LLM.get_response_stream) ---------------------

def _custom_llm_with_tool_round():
    """Bare ``LLM`` whose stream requests tool ``f`` then answers non-streamed."""
    from praisonaiagents.llm.llm import LLM

    llm = LLM.__new__(LLM)
    llm.model = "gpt-4o"
    llm.tool_timeout_ms = None
    llm._build_messages = lambda **kwargs: ([{"role": "user", "content": kwargs["prompt"]}], kwargs["prompt"])
    llm._format_tools_for_litellm = lambda tools: [{"type": "function", "function": {"name": "f"}}]
    llm._supports_streaming_tools = lambda: True
    llm._build_completion_params = lambda **kwargs: kwargs
    llm._is_ollama_provider = lambda: False
    llm._register_deferred_if_any = lambda result: None
    # ``LLM._create_tool_message`` does not exist on main (the existing
    # dispatch test stubs it too); without it the tool round falls back to
    # non-streaming and this test would pass through the wrong path.
    llm._create_tool_message = lambda name, result, call_id, is_ollama: {
        "role": "tool", "tool_call_id": call_id, "content": str(result),
    }

    completion_calls = []

    def completion(**kwargs):
        completion_calls.append(kwargs)
        if kwargs["stream"]:
            return iter([
                _chunk(tool_calls=[_tool_call_delta(0, "call_1", "f", "")]),
                _chunk(tool_calls=[_tool_call_delta(0, None, None, '{"x": 21}')]),
                _chunk(finish_reason="tool_calls"),
            ])
        message = types.SimpleNamespace(content="final answer", tool_calls=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message, finish_reason="stop")])

    llm._completion_with_retry = completion

    executed = []

    def execute_tool_fn(function_name, arguments, tool_call_id=None, **_):
        executed.append((function_name, arguments))
        return arguments["x"] * 2

    def run():
        return list(llm.get_response_stream(
            "double 21", tools=[lambda: None], execute_tool_fn=execute_tool_fn,
        ))

    return run, completion_calls, executed


def test_get_response_stream_fires_tool_call_callback(tool_call_events):
    run, completion_calls, executed = _custom_llm_with_tool_round()

    chunks = run()

    assert executed == [("f", {"x": 21})]
    assert "".join(chunks) == "final answer"
    # Streamed tool round, then the non-streaming follow-up that carries the
    # tool result -- not the "streaming failed" fallback, which carries none.
    assert [c["stream"] for c in completion_calls] == [True, False]
    assert completion_calls[1]["messages"][-1] == {
        "role": "tool", "tool_call_id": "call_1", "content": "42",
    }

    assert len(tool_call_events) == 1, tool_call_events
    event = tool_call_events[0]
    assert event["tool_name"] == "f"
    assert event["tool_input"] == {"x": 21}
    assert event["tool_output"] == "42"
    assert event["success"] is True


def test_get_response_stream_survives_a_raising_tool_call_callback():
    """Best-effort on the custom-LLM path too: a raising callback must not
    knock the stream into the 'streaming failed' fallback."""
    events = []

    def exploding(**kwargs):
        events.append(kwargs)
        raise RuntimeError("UI is gone")

    with main_module._callbacks_lock:
        previous = main_module.sync_display_callbacks.get('tool_call')
    register_display_callback('tool_call', exploding)
    try:
        run, completion_calls, executed = _custom_llm_with_tool_round()
        chunks = run()
    finally:
        with main_module._callbacks_lock:
            if previous is None:
                main_module.sync_display_callbacks.pop('tool_call', None)
            else:
                main_module.sync_display_callbacks['tool_call'] = previous

    assert len(events) == 1 and events[0]["tool_name"] == "f"
    assert executed == [("f", {"x": 21})]
    assert "".join(chunks) == "final answer"
    # The follow-up (not the fallback) ran: its last message is the tool result.
    assert [c["stream"] for c in completion_calls] == [True, False]
    assert completion_calls[1]["messages"][-1] == {
        "role": "tool", "tool_call_id": "call_1", "content": "42",
    }
