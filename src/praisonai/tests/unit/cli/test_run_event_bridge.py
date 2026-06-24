"""Tests for the `praisonai run` stream-json event bridge.

Verifies that core agent stream events are mapped onto the CLI
OutputController as a stable, versioned NDJSON event stream and that the
bridge is a no-op in non-JSON modes.
"""

import json

import pytest

from praisonai.cli.output.console import OutputController, OutputMode
from praisonai.cli.output.event_bridge import (
    SCHEMA_VERSION,
    StreamEventBridge,
    attach_bridge,
    detach_bridge,
)


class _FakeEnum:
    """Mimic core StreamEventType members which expose `.value`."""

    def __init__(self, value):
        self.value = value


class _FakeStreamEvent:
    def __init__(self, type_value, content=None, tool_call=None,
                 error=None, is_reasoning=False, agent_id=None):
        self.type = _FakeEnum(type_value)
        self.content = content
        self.tool_call = tool_call
        self.error = error
        self.is_reasoning = is_reasoning
        self.agent_id = agent_id


class _FakeEmitter:
    """Minimal stand-in for core StreamEventEmitter."""

    def __init__(self):
        self.callbacks = []

    def add_callback(self, cb):
        self.callbacks.append(cb)

    def remove_callback(self, cb):
        if cb in self.callbacks:
            self.callbacks.remove(cb)

    def emit(self, event):
        for cb in list(self.callbacks):
            cb(event)


class _FakeAgent:
    def __init__(self):
        self.stream_emitter = _FakeEmitter()


def _capture(capsys):
    out = capsys.readouterr().out.strip().splitlines()
    return [json.loads(line) for line in out if line.strip()]


def test_bridge_inactive_in_text_mode():
    output = OutputController(mode=OutputMode.TEXT)
    bridge = StreamEventBridge(output)
    assert bridge.active is False


def test_bridge_active_in_stream_json_mode():
    output = OutputController(mode=OutputMode.STREAM_JSON)
    bridge = StreamEventBridge(output)
    assert bridge.active is True


def test_tool_events_mapped_to_ndjson(capsys):
    output = OutputController(mode=OutputMode.STREAM_JSON)
    agent = _FakeAgent()
    bridge = attach_bridge(agent, output)
    assert bridge is not None

    agent.stream_emitter.emit(_FakeStreamEvent(
        "tool_call_start", tool_call={"name": "edit_file", "arguments": {"path": "x"}}))
    agent.stream_emitter.emit(_FakeStreamEvent(
        "tool_call_result", tool_call={"name": "edit_file", "result": "ok"}))

    events = _capture(capsys)
    types = [e["event"] for e in events]
    assert "tool.start" in types
    assert "tool.result" in types

    start = next(e for e in events if e["event"] == "tool.start")
    assert start["data"]["schema_version"] == SCHEMA_VERSION
    assert start["data"]["tool"] == "edit_file"
    assert start["data"]["args"] == {"path": "x"}

    result = next(e for e in events if e["event"] == "tool.result")
    assert result["data"]["ok"] is True


def test_text_and_reasoning_delta(capsys):
    output = OutputController(mode=OutputMode.STREAM_JSON)
    agent = _FakeAgent()
    attach_bridge(agent, output)

    agent.stream_emitter.emit(_FakeStreamEvent("delta_text", content="hello"))
    agent.stream_emitter.emit(_FakeStreamEvent("delta_text", content="why", is_reasoning=True))

    events = _capture(capsys)
    types = {e["event"] for e in events}
    assert "text.delta" in types
    assert "reasoning.delta" in types


def test_error_event_mapped(capsys):
    output = OutputController(mode=OutputMode.STREAM_JSON)
    agent = _FakeAgent()
    attach_bridge(agent, output)

    agent.stream_emitter.emit(_FakeStreamEvent("error", error="boom"))

    events = _capture(capsys)
    assert any(e["event"] == "tool.error" and e["data"]["error"] == "boom" for e in events)


def test_run_lifecycle_helpers(capsys):
    output = OutputController(mode=OutputMode.STREAM_JSON)
    bridge = StreamEventBridge(output)
    bridge.emit_run_start({"agent": "A"})
    bridge.emit_agent_message("A")
    bridge.emit_run_result("done", ok=True)

    events = _capture(capsys)
    types = [e["event"] for e in events]
    assert types == ["run.start", "agent.message", "run.result"]
    assert events[-1]["data"]["ok"] is True
    assert events[-1]["data"]["result"] == "done"
    for e in events:
        assert e["data"]["schema_version"] == SCHEMA_VERSION


def test_run_error_event(capsys):
    output = OutputController(mode=OutputMode.STREAM_JSON)
    bridge = StreamEventBridge(output)
    bridge.emit_run_error("failed")

    events = _capture(capsys)
    assert events[-1]["event"] == "run.error"
    assert events[-1]["data"]["ok"] is False
    assert events[-1]["data"]["error"] == "failed"


def test_no_output_in_text_mode(capsys):
    output = OutputController(mode=OutputMode.TEXT)
    agent = _FakeAgent()
    bridge = attach_bridge(agent, output)
    # Bridge not attached in text mode -> emitter has no callbacks.
    assert bridge is None
    agent.stream_emitter.emit(_FakeStreamEvent(
        "tool_call_start", tool_call={"name": "x"}))
    assert capsys.readouterr().out.strip() == ""


def test_detach_removes_callback(capsys):
    output = OutputController(mode=OutputMode.STREAM_JSON)
    agent = _FakeAgent()
    bridge = attach_bridge(agent, output)
    detach_bridge(agent, bridge)
    agent.stream_emitter.emit(_FakeStreamEvent(
        "tool_call_start", tool_call={"name": "x"}))
    assert capsys.readouterr().out.strip() == ""
