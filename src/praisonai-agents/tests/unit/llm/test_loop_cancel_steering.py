"""
Tests for cooperative cancellation and mid-run steering inside the
OpenAI-native tool-calling loop (openai_client.chat_completion_with_tools).

These exercise the loop directly with a mocked model call so no network or
real LLM is required, verifying:
- interrupt stops the loop between iterations,
- a pending interrupt prevents tool dispatch on that iteration,
- steering messages are injected as user messages before the next model call,
- absence of controller/steering is a no-op.
"""

from types import SimpleNamespace

import pytest

from praisonaiagents.agent.interrupt import InterruptController
from praisonaiagents.agent.message_steering import SteeringMixin
from praisonaiagents.llm.openai_client import OpenAIClient


class _Steerable(SteeringMixin):
    def __init__(self):
        self._init_message_steering(True)


def test_drain_steering_messages_returns_all_pending():
    s = _Steerable()
    s.steer("note one")
    s.steer("note two")
    notes = s._drain_steering_messages()
    joined = "\n".join(notes)
    assert "note one" in joined and "note two" in joined
    # Draining a second time yields nothing (queue emptied)
    assert s._drain_steering_messages() == []


def test_drain_steering_messages_preserves_interrupt_priority():
    # A mid-run interrupt-priority steer must not be downgraded to normal
    # guidance when drained and injected between tool iterations.
    from praisonaiagents.agent.protocols import SteeringPriority

    s = _Steerable()
    s.steer("stop and pivot", priority=SteeringPriority.INTERRUPT.value)
    s.steer("also consider Y", priority=SteeringPriority.NORMAL.value)
    notes = s._drain_steering_messages()

    interrupt_note = next((n for n in notes if "stop and pivot" in n), None)
    normal_note = next((n for n in notes if "also consider Y" in n), None)
    assert interrupt_note is not None and "[INTERRUPT USER GUIDANCE]" in interrupt_note
    assert normal_note is not None and "[USER GUIDANCE]" in normal_note


def test_drain_steering_messages_noop_when_disabled():
    class _NoSteer(SteeringMixin):
        def __init__(self):
            self._init_message_steering(False)

    assert _NoSteer()._drain_steering_messages() == []


def _tool_call(idx=0):
    return SimpleNamespace(
        id=f"call_{idx}",
        type="function",
        function=SimpleNamespace(name="do_thing", arguments="{}"),
    )


def _response_with_tools(content="", tools=True):
    message = SimpleNamespace(
        content=content,
        tool_calls=[_tool_call()] if tools else None,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


@pytest.fixture
def client(monkeypatch):
    c = OpenAIClient(api_key="test-key")
    return c


def _make_client_returning_tools(monkeypatch, call_counter):
    c = OpenAIClient(api_key="test-key")

    def fake_process_stream_response(*args, **kwargs):
        call_counter.append(1)
        # Always return a response asking for another tool call
        return _response_with_tools()

    monkeypatch.setattr(c, "process_stream_response", fake_process_stream_response)
    return c


def test_interrupt_stops_loop_between_iterations(monkeypatch):
    calls = []
    tool_runs = []
    c = _make_client_returning_tools(monkeypatch, calls)
    controller = InterruptController()

    def execute_tool_fn(name, args, **kw):
        tool_runs.append(name)
        # Request cancellation after the first tool runs
        controller.request("user /stop")
        return "ok"

    c.chat_completion_with_tools(
        messages=[{"role": "user", "content": "go"}],
        tools=[],
        execute_tool_fn=execute_tool_fn,
        stream=True,
        verbose=False,
        max_iterations=5,
        cancel_token=controller,
    )

    # First iteration makes a model call and runs the tool; the loop must then
    # halt at the top of iteration 2 rather than making more model calls.
    assert len(calls) == 1
    assert tool_runs == ["do_thing"]
    assert c._last_stop_reason == "cancelled"


def test_interrupt_before_tool_dispatch(monkeypatch):
    calls = []
    tool_runs = []
    c = _make_client_returning_tools(monkeypatch, calls)
    controller = InterruptController()
    # Pre-set the interrupt: model call happens, but tools must not dispatch.
    controller.request("preempt")

    def execute_tool_fn(name, args, **kw):
        tool_runs.append(name)
        return "ok"

    c.chat_completion_with_tools(
        messages=[{"role": "user", "content": "go"}],
        tools=[],
        execute_tool_fn=execute_tool_fn,
        stream=True,
        verbose=False,
        max_iterations=5,
        cancel_token=controller,
    )

    # Cancellation is checked at the top of the loop, so no model call and no
    # tool execution happen.
    assert tool_runs == []
    assert c._last_stop_reason == "cancelled"


def test_steering_injected_mid_run(monkeypatch):
    calls = []
    seen_messages = []
    c = OpenAIClient(api_key="test-key")

    iteration = {"n": 0}

    def fake_process_stream_response(*args, **kwargs):
        # Capture the messages the model sees on this call
        msgs = kwargs.get("messages") or (args[0] if args else None)
        seen_messages.append(list(msgs))
        calls.append(1)
        iteration["n"] += 1
        # First call asks for a tool, second returns no tools (finish)
        return _response_with_tools(tools=iteration["n"] == 1)

    monkeypatch.setattr(c, "process_stream_response", fake_process_stream_response)

    drained = {"done": False}

    def steering_drain():
        if drained["done"]:
            return []
        drained["done"] = True
        return ["focus on X"]

    def execute_tool_fn(name, args, **kw):
        return "ok"

    c.chat_completion_with_tools(
        messages=[{"role": "user", "content": "go"}],
        tools=[],
        execute_tool_fn=execute_tool_fn,
        stream=True,
        verbose=False,
        max_iterations=5,
        steering_drain=steering_drain,
    )

    # The steering note must appear as a user message before the FIRST model call.
    first_call_msgs = seen_messages[0]
    assert any(
        m.get("role") == "user" and "[steering] focus on X" in str(m.get("content", ""))
        for m in first_call_msgs
    ), first_call_msgs


def test_no_controller_is_noop(monkeypatch):
    calls = []
    c = OpenAIClient(api_key="test-key")

    iteration = {"n": 0}

    def fake_process_stream_response(*args, **kwargs):
        calls.append(1)
        iteration["n"] += 1
        return _response_with_tools(tools=iteration["n"] == 1)

    monkeypatch.setattr(c, "process_stream_response", fake_process_stream_response)

    def execute_tool_fn(name, args, **kw):
        return "ok"

    c.chat_completion_with_tools(
        messages=[{"role": "user", "content": "go"}],
        tools=[],
        execute_tool_fn=execute_tool_fn,
        stream=True,
        verbose=False,
        max_iterations=5,
    )

    # Without a controller/steering, the loop runs to a natural finish.
    assert c._last_stop_reason == "completed"
    assert len(calls) == 2
