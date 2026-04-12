"""Tests for provider-agnostic managed event types."""

import time
from praisonaiagents.managed.events import (
    ManagedEvent,
    AgentMessageEvent,
    ToolUseEvent,
    CustomToolUseEvent,
    ToolConfirmationEvent,
    SessionIdleEvent,
    SessionRunningEvent,
    SessionErrorEvent,
    UsageEvent,
    EventType,
    StopReason,
)


class TestEventType:
    def test_event_type_values(self):
        assert EventType.AGENT_MESSAGE == "agent.message"
        assert EventType.AGENT_TOOL_USE == "agent.tool_use"
        assert EventType.AGENT_CUSTOM_TOOL_USE == "agent.custom_tool_use"
        assert EventType.TOOL_CONFIRMATION == "agent.tool_confirmation"
        assert EventType.SESSION_IDLE == "session.status_idle"
        assert EventType.SESSION_RUNNING == "session.status_running"
        assert EventType.SESSION_ERROR == "session.error"
        assert EventType.USAGE == "session.usage"

    def test_stop_reason_values(self):
        assert StopReason.END_TURN == "end_turn"
        assert StopReason.REQUIRES_ACTION == "requires_action"
        assert StopReason.MAX_TURNS == "max_turns"
        assert StopReason.INTERRUPTED == "interrupted"
        assert StopReason.ERROR == "error"


class TestManagedEvent:
    def test_base_event_defaults(self):
        e = ManagedEvent()
        assert e.type == ""
        assert e.metadata == {}
        assert isinstance(e.timestamp, float)

    def test_base_event_custom_type(self):
        e = ManagedEvent(type="custom.event")
        assert e.type == "custom.event"

    def test_timestamp_auto_set(self):
        before = time.time()
        e = ManagedEvent()
        after = time.time()
        assert before <= e.timestamp <= after


class TestAgentMessageEvent:
    def test_auto_type(self):
        e = AgentMessageEvent(content=[{"type": "text", "text": "hello"}])
        assert e.type == "agent.message"

    def test_text_property_single(self):
        e = AgentMessageEvent(content=[{"type": "text", "text": "hello"}])
        assert e.text == "hello"

    def test_text_property_multiple(self):
        e = AgentMessageEvent(content=[
            {"type": "text", "text": "hello "},
            {"type": "text", "text": "world"},
        ])
        assert e.text == "hello world"

    def test_text_property_empty(self):
        e = AgentMessageEvent()
        assert e.text == ""

    def test_text_property_mixed_blocks(self):
        e = AgentMessageEvent(content=[
            {"type": "text", "text": "code: "},
            {"type": "image", "url": "..."},
            {"type": "text", "text": "done"},
        ])
        assert e.text == "code: done"


class TestToolUseEvent:
    def test_auto_type(self):
        e = ToolUseEvent(name="bash", tool_use_id="t1")
        assert e.type == "agent.tool_use"

    def test_fields(self):
        e = ToolUseEvent(
            name="read",
            input={"path": "/tmp/test.py"},
            tool_use_id="t2",
            needs_confirmation=True,
        )
        assert e.name == "read"
        assert e.input == {"path": "/tmp/test.py"}
        assert e.tool_use_id == "t2"
        assert e.needs_confirmation is True

    def test_defaults(self):
        e = ToolUseEvent()
        assert e.name == ""
        assert e.input == {}
        assert e.tool_use_id == ""
        assert e.needs_confirmation is False


class TestCustomToolUseEvent:
    def test_auto_type(self):
        e = CustomToolUseEvent(name="my_tool")
        assert e.type == "agent.custom_tool_use"

    def test_fields(self):
        e = CustomToolUseEvent(
            name="calculator",
            input={"expression": "2+2"},
            tool_use_id="ct1",
        )
        assert e.name == "calculator"
        assert e.input == {"expression": "2+2"}


class TestToolConfirmationEvent:
    def test_auto_type(self):
        e = ToolConfirmationEvent(name="bash", tool_use_id="tc1")
        assert e.type == "agent.tool_confirmation"


class TestSessionIdleEvent:
    def test_auto_type(self):
        e = SessionIdleEvent()
        assert e.type == "session.status_idle"

    def test_default_stop_reason(self):
        e = SessionIdleEvent()
        assert e.stop_reason == "end_turn"

    def test_custom_stop_reason(self):
        e = SessionIdleEvent(stop_reason=StopReason.MAX_TURNS.value)
        assert e.stop_reason == "max_turns"

    def test_event_ids(self):
        e = SessionIdleEvent(
            stop_reason=StopReason.REQUIRES_ACTION.value,
            event_ids=["ev1", "ev2"],
        )
        assert e.event_ids == ["ev1", "ev2"]


class TestSessionRunningEvent:
    def test_auto_type(self):
        e = SessionRunningEvent()
        assert e.type == "session.status_running"


class TestSessionErrorEvent:
    def test_auto_type(self):
        e = SessionErrorEvent(error_message="something broke")
        assert e.type == "session.error"

    def test_fields(self):
        e = SessionErrorEvent(
            error_message="timeout",
            error_code="TIMEOUT",
        )
        assert e.error_message == "timeout"
        assert e.error_code == "TIMEOUT"


class TestUsageEvent:
    def test_auto_type(self):
        e = UsageEvent(input_tokens=100, output_tokens=50)
        assert e.type == "session.usage"

    def test_fields(self):
        e = UsageEvent(
            input_tokens=1000,
            output_tokens=500,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=100,
        )
        assert e.input_tokens == 1000
        assert e.output_tokens == 500
        assert e.cache_creation_input_tokens == 200
        assert e.cache_read_input_tokens == 100

    def test_defaults(self):
        e = UsageEvent()
        assert e.input_tokens == 0
        assert e.output_tokens == 0
        assert e.cache_creation_input_tokens == 0
        assert e.cache_read_input_tokens == 0


class TestManagedEventMetadata:
    def test_metadata_passthrough(self):
        e = AgentMessageEvent(
            content=[{"type": "text", "text": "hi"}],
            metadata={"provider": "anthropic", "request_id": "abc123"},
        )
        assert e.metadata["provider"] == "anthropic"
        assert e.metadata["request_id"] == "abc123"
