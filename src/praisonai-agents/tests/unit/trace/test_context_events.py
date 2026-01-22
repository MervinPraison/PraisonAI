"""
Tests for context events module.

TDD tests for ContextEvent, ContextEventType, and context trace sinks.
These tests define the expected behavior for the context replay feature.
"""

import json
import time


class TestContextEventType:
    """Tests for ContextEventType enum."""
    
    def test_context_event_types_exist(self):
        """Test all required context event types exist."""
        from praisonaiagents.trace.context_events import ContextEventType
        
        required_types = [
            "SESSION_START",
            "SESSION_END",
            "AGENT_START",
            "AGENT_END",
            "AGENT_HANDOFF",
            "MESSAGE_ADDED",
            "TOOL_CALL_START",
            "TOOL_CALL_END",
            "LLM_REQUEST",
            "LLM_RESPONSE",
            "CONTEXT_SNAPSHOT",
        ]
        
        for event_type in required_types:
            assert hasattr(ContextEventType, event_type), f"Missing event type: {event_type}"
    
    def test_context_event_type_values(self):
        """Test event type string values."""
        from praisonaiagents.trace.context_events import ContextEventType
        
        assert ContextEventType.SESSION_START.value == "session_start"
        assert ContextEventType.AGENT_START.value == "agent_start"
        assert ContextEventType.MESSAGE_ADDED.value == "message_added"
        assert ContextEventType.TOOL_CALL_START.value == "tool_call_start"


class TestGlobalEmitterRegistry:
    """Tests for global emitter registry using contextvars."""
    
    def test_get_context_emitter_returns_noop_by_default(self):
        """Test that get_context_emitter returns a disabled NoOp emitter when not set."""
        from praisonaiagents.trace.context_events import (
            get_context_emitter, ContextListSink
        )
        
        emitter = get_context_emitter()
        
        # Should return an emitter (not None)
        assert emitter is not None
        # Should be disabled by default
        assert emitter.enabled == False
    
    def test_set_context_emitter_and_get(self):
        """Test that set_context_emitter sets the emitter for current context."""
        from praisonaiagents.trace.context_events import (
            get_context_emitter, set_context_emitter, reset_context_emitter,
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test-session", enabled=True)
        
        # Set the emitter
        token = set_context_emitter(emitter)
        
        try:
            # Get should return the same emitter
            retrieved = get_context_emitter()
            assert retrieved is emitter
            assert retrieved.enabled == True
            assert retrieved.session_id == "test-session"
        finally:
            # Reset to avoid affecting other tests
            reset_context_emitter(token)
    
    def test_reset_context_emitter(self):
        """Test that reset_context_emitter restores previous state."""
        from praisonaiagents.trace.context_events import (
            get_context_emitter, set_context_emitter, reset_context_emitter,
            ContextTraceEmitter, ContextListSink
        )
        
        # Get default (disabled)
        default_emitter = get_context_emitter()
        assert default_emitter.enabled == False
        
        # Set a new emitter
        sink = ContextListSink()
        new_emitter = ContextTraceEmitter(sink=sink, session_id="new", enabled=True)
        token = set_context_emitter(new_emitter)
        
        # Verify it's set
        assert get_context_emitter() is new_emitter
        
        # Reset
        reset_context_emitter(token)
        
        # Should be back to disabled default
        restored = get_context_emitter()
        assert restored.enabled == False
    
    def test_context_emitter_emits_to_sink_when_set(self):
        """Test that events are emitted to the sink when emitter is set."""
        from praisonaiagents.trace.context_events import (
            get_context_emitter, set_context_emitter, reset_context_emitter,
            ContextTraceEmitter, ContextListSink, ContextEventType
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=True)
        token = set_context_emitter(emitter)
        
        try:
            # Get emitter and emit events
            e = get_context_emitter()
            e.agent_start("test-agent")
            e.agent_end("test-agent")
            
            # Verify events were captured
            events = sink.get_events()
            assert len(events) == 2
            assert events[0].event_type == ContextEventType.AGENT_START
            assert events[1].event_type == ContextEventType.AGENT_END
        finally:
            reset_context_emitter(token)
    
    def test_context_emitter_noop_when_not_set(self):
        """Test that events are discarded when emitter is not set (NoOp)."""
        from praisonaiagents.trace.context_events import get_context_emitter
        
        # Get default emitter (should be NoOp/disabled)
        emitter = get_context_emitter()
        
        # These should not raise, just be no-ops
        emitter.agent_start("test")
        emitter.tool_call_start("test", "some_tool")
        emitter.agent_end("test")
        
        # No way to verify NoOp discarded events, but no exception = success


class TestContextEvent:
    """Tests for ContextEvent dataclass."""
    
    def test_context_event_creation_minimal(self):
        """Test creating ContextEvent with minimal fields."""
        from praisonaiagents.trace.context_events import ContextEvent, ContextEventType
        
        event = ContextEvent(
            event_type=ContextEventType.AGENT_START,
            timestamp=1736665496.123,
            session_id="sess-123",
        )
        
        assert event.event_type == ContextEventType.AGENT_START
        assert event.timestamp == 1736665496.123
        assert event.session_id == "sess-123"
        assert event.sequence_num == 0
        assert event.agent_name is None
    
    def test_context_event_creation_full(self):
        """Test creating ContextEvent with all fields."""
        from praisonaiagents.trace.context_events import ContextEvent, ContextEventType
        
        event = ContextEvent(
            event_type=ContextEventType.MESSAGE_ADDED,
            timestamp=1736665497.456,
            session_id="sess-456",
            agent_name="researcher",
            sequence_num=5,
            messages_count=10,
            tokens_used=1500,
            tokens_budget=128000,
            data={"role": "user", "content": "Hello"},
        )
        
        assert event.event_type == ContextEventType.MESSAGE_ADDED
        assert event.agent_name == "researcher"
        assert event.sequence_num == 5
        assert event.messages_count == 10
        assert event.tokens_used == 1500
        assert event.tokens_budget == 128000
        assert event.data == {"role": "user", "content": "Hello"}
    
    def test_context_event_to_dict(self):
        """Test ContextEvent.to_dict() method."""
        from praisonaiagents.trace.context_events import ContextEvent, ContextEventType
        
        event = ContextEvent(
            event_type=ContextEventType.AGENT_START,
            timestamp=1736665496.123,
            session_id="sess-123",
            agent_name="writer",
        )
        
        d = event.to_dict()
        
        assert d["event_type"] == "agent_start"
        assert d["timestamp"] == 1736665496.123
        assert d["session_id"] == "sess-123"
        assert d["agent_name"] == "writer"
        assert "sequence_num" in d
    
    def test_context_event_to_json(self):
        """Test ContextEvent.to_json() method."""
        from praisonaiagents.trace.context_events import ContextEvent, ContextEventType
        
        event = ContextEvent(
            event_type=ContextEventType.TOOL_CALL_START,
            timestamp=1736665497.0,
            session_id="sess-789",
            agent_name="coder",
            data={"tool_name": "read_file", "args": {"path": "/tmp/test.txt"}},
        )
        
        json_str = event.to_json()
        parsed = json.loads(json_str)
        
        assert parsed["event_type"] == "tool_call_start"
        assert parsed["session_id"] == "sess-789"
        assert parsed["data"]["tool_name"] == "read_file"
    
    def test_context_event_from_dict(self):
        """Test ContextEvent.from_dict() class method."""
        from praisonaiagents.trace.context_events import ContextEvent, ContextEventType
        
        data = {
            "event_type": "agent_end",
            "timestamp": 1736665500.0,
            "session_id": "sess-abc",
            "agent_name": "analyst",
            "sequence_num": 10,
            "messages_count": 5,
            "tokens_used": 2000,
            "tokens_budget": 128000,
            "data": {"status": "completed"},
        }
        
        event = ContextEvent.from_dict(data)
        
        assert event.event_type == ContextEventType.AGENT_END
        assert event.session_id == "sess-abc"
        assert event.agent_name == "analyst"
        assert event.sequence_num == 10
        assert event.data == {"status": "completed"}


class TestContextTraceSink:
    """Tests for ContextTraceSink protocol."""
    
    def test_context_noop_sink(self):
        """Test ContextNoOpSink does nothing."""
        from praisonaiagents.trace.context_events import ContextNoOpSink, ContextEvent, ContextEventType
        
        sink = ContextNoOpSink()
        event = ContextEvent(
            event_type=ContextEventType.AGENT_START,
            timestamp=time.time(),
            session_id="test",
        )
        
        # Should not raise
        sink.emit(event)
        sink.flush()
        sink.close()
    
    def test_context_list_sink(self):
        """Test ContextListSink collects events."""
        from praisonaiagents.trace.context_events import ContextListSink, ContextEvent, ContextEventType
        
        sink = ContextListSink()
        
        event1 = ContextEvent(
            event_type=ContextEventType.SESSION_START,
            timestamp=1.0,
            session_id="test",
        )
        event2 = ContextEvent(
            event_type=ContextEventType.AGENT_START,
            timestamp=2.0,
            session_id="test",
            agent_name="researcher",
        )
        
        sink.emit(event1)
        sink.emit(event2)
        
        events = sink.get_events()
        assert len(events) == 2
        assert events[0].event_type == ContextEventType.SESSION_START
        assert events[1].event_type == ContextEventType.AGENT_START
        assert events[1].agent_name == "researcher"
    
    def test_context_list_sink_clear(self):
        """Test ContextListSink.clear() method."""
        from praisonaiagents.trace.context_events import ContextListSink, ContextEvent, ContextEventType
        
        sink = ContextListSink()
        sink.emit(ContextEvent(
            event_type=ContextEventType.AGENT_START,
            timestamp=1.0,
            session_id="test",
        ))
        
        assert len(sink.get_events()) == 1
        
        sink.clear()
        
        assert len(sink.get_events()) == 0


class TestContextTraceEmitter:
    """Tests for ContextTraceEmitter class."""
    
    def test_emitter_session_lifecycle(self):
        """Test emitter session start/end events."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink, ContextEventType
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test-session")
        
        emitter.session_start()
        emitter.session_end()
        
        events = sink.get_events()
        assert len(events) == 2
        assert events[0].event_type == ContextEventType.SESSION_START
        assert events[1].event_type == ContextEventType.SESSION_END
        assert events[0].session_id == "test-session"
    
    def test_emitter_agent_lifecycle(self):
        """Test emitter agent start/end events."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink, ContextEventType
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test-session")
        
        emitter.agent_start("researcher")
        emitter.agent_end("researcher")
        
        events = sink.get_events()
        assert len(events) == 2
        assert events[0].event_type == ContextEventType.AGENT_START
        assert events[0].agent_name == "researcher"
        assert events[1].event_type == ContextEventType.AGENT_END
    
    def test_emitter_message_added(self):
        """Test emitter message added event."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink, ContextEventType
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test-session")
        
        emitter.message_added(
            agent_name="writer",
            role="user",
            content="Hello, world!",
            messages_count=1,
            tokens_used=10,
        )
        
        events = sink.get_events()
        assert len(events) == 1
        assert events[0].event_type == ContextEventType.MESSAGE_ADDED
        assert events[0].agent_name == "writer"
        assert events[0].messages_count == 1
        assert events[0].data["role"] == "user"
        assert events[0].data["content"] == "Hello, world!"
    
    def test_emitter_tool_call(self):
        """Test emitter tool call start/end events."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink, ContextEventType
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test-session")
        
        emitter.tool_call_start(
            agent_name="coder",
            tool_name="read_file",
            tool_args={"path": "/tmp/test.txt"},
        )
        emitter.tool_call_end(
            agent_name="coder",
            tool_name="read_file",
            result="file contents here",
            duration_ms=50.5,
        )
        
        events = sink.get_events()
        assert len(events) == 2
        assert events[0].event_type == ContextEventType.TOOL_CALL_START
        assert events[0].data["tool_name"] == "read_file"
        assert events[1].event_type == ContextEventType.TOOL_CALL_END
        assert events[1].data["duration_ms"] == 50.5
    
    def test_emitter_llm_request_response(self):
        """Test emitter LLM request/response events."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink, ContextEventType
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test-session")
        
        emitter.llm_request(
            agent_name="analyst",
            messages_count=5,
            tokens_used=1000,
            tokens_budget=128000,
        )
        emitter.llm_response(
            agent_name="analyst",
            response_tokens=500,
            duration_ms=1500.0,
        )
        
        events = sink.get_events()
        assert len(events) == 2
        assert events[0].event_type == ContextEventType.LLM_REQUEST
        assert events[0].tokens_used == 1000
        assert events[1].event_type == ContextEventType.LLM_RESPONSE
        assert events[1].data["response_tokens"] == 500
    
    def test_emitter_context_snapshot(self):
        """Test emitter context snapshot event."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink, ContextEventType
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test-session")
        
        emitter.context_snapshot(
            agent_name="researcher",
            messages_count=10,
            tokens_used=5000,
            tokens_budget=128000,
            messages=[
                {"role": "system", "content": "You are a researcher"},
                {"role": "user", "content": "Find info about AI"},
            ],
        )
        
        events = sink.get_events()
        assert len(events) == 1
        assert events[0].event_type == ContextEventType.CONTEXT_SNAPSHOT
        assert events[0].messages_count == 10
        assert len(events[0].data["messages"]) == 2
    
    def test_emitter_disabled(self):
        """Test emitter when disabled."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=False)
        
        emitter.session_start()
        emitter.agent_start("test")
        emitter.message_added("test", "user", "hello", 1, 10)
        
        # No events should be emitted
        assert len(sink.get_events()) == 0
    
    def test_emitter_sequence_numbers(self):
        """Test that emitter assigns sequential sequence numbers."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test-session")
        
        emitter.session_start()
        emitter.agent_start("agent1")
        emitter.message_added("agent1", "user", "hello", 1, 10)
        emitter.agent_end("agent1")
        emitter.session_end()
        
        events = sink.get_events()
        assert len(events) == 5
        
        for i, event in enumerate(events):
            assert event.sequence_num == i, f"Event {i} has wrong sequence_num: {event.sequence_num}"
    
    def test_emitter_redacts_sensitive_data(self):
        """Test that emitter redacts sensitive data in tool args."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", redact=True)
        
        emitter.tool_call_start(
            agent_name="api_caller",
            tool_name="call_api",
            tool_args={"api_key": "sk-secret123", "query": "test"},
        )
        
        events = sink.get_events()
        assert events[0].data["tool_args"]["api_key"] == "[REDACTED]"
        assert events[0].data["tool_args"]["query"] == "test"
    
    def test_emitter_agent_handoff(self):
        """Test emitter agent handoff event for tracking agent flow."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink, ContextEventType
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test-session")
        
        emitter.agent_handoff(
            from_agent="researcher",
            to_agent="writer",
            reason="Research complete, passing to writer",
            context_passed={"findings": ["result1", "result2"]},
        )
        
        events = sink.get_events()
        assert len(events) == 1
        assert events[0].event_type == ContextEventType.AGENT_HANDOFF
        assert events[0].agent_name == "researcher"
        assert events[0].data["from_agent"] == "researcher"
        assert events[0].data["to_agent"] == "writer"
        assert events[0].data["reason"] == "Research complete, passing to writer"
        assert events[0].data["context_passed"]["findings"] == ["result1", "result2"]


class TestPerformance:
    """Performance tests for context events module."""
    
    def test_noop_sink_overhead(self):
        """Test that ContextNoOpSink has minimal overhead."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextNoOpSink
        )
        
        emitter = ContextTraceEmitter(sink=ContextNoOpSink(), session_id="perf-test")
        
        start = time.perf_counter()
        for _ in range(10000):
            emitter.message_added("agent", "user", "test message", 1, 100)
        elapsed = time.perf_counter() - start
        
        # Should complete 10000 iterations in under 100ms
        assert elapsed < 0.1, f"ContextNoOpSink too slow: {elapsed:.3f}s for 10000 iterations"
    
    def test_disabled_emitter_overhead(self):
        """Test that disabled emitter has near-zero overhead."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink
        )
        
        emitter = ContextTraceEmitter(sink=ContextListSink(), session_id="perf-test", enabled=False)
        
        start = time.perf_counter()
        for _ in range(10000):
            emitter.message_added("agent", "user", "test message", 1, 100)
        elapsed = time.perf_counter() - start
        
        # Should complete 10000 iterations in under 50ms when disabled
        assert elapsed < 0.05, f"Disabled emitter too slow: {elapsed:.3f}s"
    
    def test_import_time(self):
        """Test that import time is minimal (relative to base package)."""
        import subprocess
        import sys
        
        # First measure baseline import time for the base package
        baseline_code = """
import time
start = time.perf_counter()
import praisonaiagents
elapsed = (time.perf_counter() - start) * 1000
print(f"{elapsed:.1f}")
"""
        subprocess.run(
            [sys.executable, "-c", baseline_code],
            capture_output=True,
            text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai-agents",
        )
        
        # Now measure context_events import (should add minimal overhead)
        code = """
import time
import praisonaiagents  # Pre-import base
start = time.perf_counter()
from praisonaiagents.trace.context_events import ContextEvent, ContextEventType
elapsed = (time.perf_counter() - start) * 1000
print(f"{elapsed:.1f}")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai-agents",
        )
        
        if result.returncode == 0:
            import_time_ms = float(result.stdout.strip())
            # Additional import should be under 50ms (after base is loaded)
            assert import_time_ms < 50, f"Context events import too slow: {import_time_ms:.1f}ms"
