"""
Tests for the trace protocol module.

TDD tests for ActionEvent, TraceSink protocol, and redaction.
"""

import time
import json


class TestActionEvent:
    """Tests for ActionEvent dataclass."""
    
    def test_action_event_creation_minimal(self):
        """Test creating ActionEvent with minimal fields."""
        from praisonaiagents.trace.protocol import ActionEvent
        
        event = ActionEvent(
            event_type="agent_start",
            timestamp=1736665496.123,
        )
        
        assert event.event_type == "agent_start"
        assert event.timestamp == 1736665496.123
        assert event.schema_version == "1.0"
        assert event.agent_id is None
        assert event.agent_name is None
        assert event.tool_name is None
    
    def test_action_event_creation_full(self):
        """Test creating ActionEvent with all fields."""
        from praisonaiagents.trace.protocol import ActionEvent
        
        event = ActionEvent(
            event_type="tool_end",
            timestamp=1736665497.456,
            agent_id="agent-123",
            agent_name="researcher",
            tool_name="web_search",
            tool_args={"query": "AI trends"},
            tool_result_summary="Found 10 results",
            duration_ms=800.5,
            status="ok",
            error_message=None,
            metadata={"provider": "duckduckgo"},
        )
        
        assert event.event_type == "tool_end"
        assert event.agent_name == "researcher"
        assert event.tool_name == "web_search"
        assert event.tool_args == {"query": "AI trends"}
        assert event.duration_ms == 800.5
        assert event.status == "ok"
        assert event.metadata == {"provider": "duckduckgo"}
    
    def test_action_event_to_dict(self):
        """Test ActionEvent.to_dict() method."""
        from praisonaiagents.trace.protocol import ActionEvent
        
        event = ActionEvent(
            event_type="agent_start",
            timestamp=1736665496.123,
            agent_name="writer",
        )
        
        d = event.to_dict()
        
        assert d["schema_version"] == "1.0"
        assert d["event_type"] == "agent_start"
        assert d["timestamp"] == 1736665496.123
        assert d["agent_name"] == "writer"
        # None values should be excluded
        assert "tool_name" not in d or d["tool_name"] is None
    
    def test_action_event_to_json(self):
        """Test ActionEvent.to_json() method."""
        from praisonaiagents.trace.protocol import ActionEvent
        
        event = ActionEvent(
            event_type="tool_start",
            timestamp=1736665497.0,
            tool_name="read_file",
            tool_args={"path": "/tmp/test.txt"},
        )
        
        json_str = event.to_json()
        parsed = json.loads(json_str)
        
        assert parsed["event_type"] == "tool_start"
        assert parsed["tool_name"] == "read_file"
        assert parsed["tool_args"] == {"path": "/tmp/test.txt"}
    
    def test_action_event_types(self):
        """Test all valid event types."""
        from praisonaiagents.trace.protocol import ActionEvent, ActionEventType
        
        valid_types = [
            ActionEventType.AGENT_START,
            ActionEventType.AGENT_END,
            ActionEventType.TOOL_START,
            ActionEventType.TOOL_END,
            ActionEventType.ERROR,
            ActionEventType.OUTPUT,
        ]
        
        for event_type in valid_types:
            event = ActionEvent(
                event_type=event_type.value,
                timestamp=time.time(),
            )
            assert event.event_type == event_type.value


class TestRedaction:
    """Tests for redaction functionality."""
    
    def test_redact_api_key(self):
        """Test redacting api_key field."""
        from praisonaiagents.trace.redact import redact_dict
        
        data = {"api_key": "sk-1234567890abcdef", "query": "hello"}
        redacted = redact_dict(data)
        
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["query"] == "hello"
    
    def test_redact_multiple_sensitive_keys(self):
        """Test redacting multiple sensitive keys."""
        from praisonaiagents.trace.redact import redact_dict
        
        data = {
            "api_key": "sk-secret",
            "password": "mypassword123",
            "token": "bearer-token",
            "authorization": "Bearer xyz",
            "secret": "top-secret",
            "normal_field": "visible",
        }
        redacted = redact_dict(data)
        
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["password"] == "[REDACTED]"
        assert redacted["token"] == "[REDACTED]"
        assert redacted["authorization"] == "[REDACTED]"
        assert redacted["secret"] == "[REDACTED]"
        assert redacted["normal_field"] == "visible"
    
    def test_redact_nested_dict(self):
        """Test redacting nested dictionaries."""
        from praisonaiagents.trace.redact import redact_dict
        
        data = {
            "config": {
                "api_key": "sk-nested",
                "endpoint": "https://api.example.com",
            },
            "name": "test",
        }
        redacted = redact_dict(data)
        
        assert redacted["config"]["api_key"] == "[REDACTED]"
        assert redacted["config"]["endpoint"] == "https://api.example.com"
        assert redacted["name"] == "test"
    
    def test_redact_list_of_dicts(self):
        """Test redacting list containing dictionaries."""
        from praisonaiagents.trace.redact import redact_dict
        
        data = {
            "items": [
                {"name": "item1", "secret": "hidden1"},
                {"name": "item2", "secret": "hidden2"},
            ]
        }
        redacted = redact_dict(data)
        
        assert redacted["items"][0]["name"] == "item1"
        assert redacted["items"][0]["secret"] == "[REDACTED]"
        assert redacted["items"][1]["secret"] == "[REDACTED]"
    
    def test_redact_case_insensitive(self):
        """Test that redaction is case-insensitive."""
        from praisonaiagents.trace.redact import redact_dict
        
        data = {
            "API_KEY": "key1",
            "Api_Key": "key2",
            "apiKey": "key3",
            "APIKEY": "key4",
        }
        redacted = redact_dict(data)
        
        assert redacted["API_KEY"] == "[REDACTED]"
        assert redacted["Api_Key"] == "[REDACTED]"
        assert redacted["apiKey"] == "[REDACTED]"
        assert redacted["APIKEY"] == "[REDACTED]"
    
    def test_redact_connection_strings(self):
        """Test redacting database connection strings."""
        from praisonaiagents.trace.redact import redact_dict
        
        data = {
            "connection_string": "postgresql://user:pass@host/db",
            "database_url": "mysql://root:secret@localhost/mydb",
            "db_url": "redis://default:password@redis:6379",
        }
        redacted = redact_dict(data)
        
        assert redacted["connection_string"] == "[REDACTED]"
        assert redacted["database_url"] == "[REDACTED]"
        assert redacted["db_url"] == "[REDACTED]"
    
    def test_redact_preserves_original(self):
        """Test that redaction doesn't modify original dict."""
        from praisonaiagents.trace.redact import redact_dict
        
        original = {"api_key": "secret", "name": "test"}
        redacted = redact_dict(original)
        
        assert original["api_key"] == "secret"
        assert redacted["api_key"] == "[REDACTED]"
    
    def test_redact_empty_dict(self):
        """Test redacting empty dictionary."""
        from praisonaiagents.trace.redact import redact_dict
        
        assert redact_dict({}) == {}
    
    def test_redact_none_values(self):
        """Test handling None values."""
        from praisonaiagents.trace.redact import redact_dict
        
        data = {"api_key": None, "name": "test"}
        redacted = redact_dict(data)
        
        # None values for sensitive keys should still be redacted
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["name"] == "test"
    
    def test_redact_disabled(self):
        """Test disabling redaction."""
        from praisonaiagents.trace.redact import redact_dict
        
        data = {"api_key": "visible", "name": "test"}
        result = redact_dict(data, enabled=False)
        
        assert result["api_key"] == "visible"
        assert result["name"] == "test"


class TestTraceSink:
    """Tests for TraceSink protocol."""
    
    def test_noop_sink(self):
        """Test NoOpSink does nothing."""
        from praisonaiagents.trace.protocol import NoOpSink, ActionEvent
        
        sink = NoOpSink()
        event = ActionEvent(event_type="agent_start", timestamp=time.time())
        
        # Should not raise
        sink.emit(event)
        sink.flush()
        sink.close()
    
    def test_list_sink(self):
        """Test ListSink collects events."""
        from praisonaiagents.trace.protocol import ListSink, ActionEvent
        
        sink = ListSink()
        
        event1 = ActionEvent(event_type="agent_start", timestamp=1.0)
        event2 = ActionEvent(event_type="tool_start", timestamp=2.0)
        
        sink.emit(event1)
        sink.emit(event2)
        
        events = sink.get_events()
        assert len(events) == 2
        assert events[0].event_type == "agent_start"
        assert events[1].event_type == "tool_start"
    
    def test_list_sink_clear(self):
        """Test ListSink.clear() method."""
        from praisonaiagents.trace.protocol import ListSink, ActionEvent
        
        sink = ListSink()
        sink.emit(ActionEvent(event_type="test", timestamp=1.0))
        
        assert len(sink.get_events()) == 1
        
        sink.clear()
        
        assert len(sink.get_events()) == 0


class TestTraceEmitter:
    """Tests for TraceEmitter class."""
    
    def test_emitter_with_noop_sink(self):
        """Test TraceEmitter with NoOpSink."""
        from praisonaiagents.trace.protocol import TraceEmitter, NoOpSink
        
        emitter = TraceEmitter(sink=NoOpSink())
        
        # Should not raise
        emitter.agent_start("test-agent", agent_id="123")
        emitter.tool_start("web_search", {"query": "test"})
        emitter.tool_end("web_search", duration_ms=100, status="ok")
        emitter.agent_end("test-agent", duration_ms=500)
    
    def test_emitter_with_list_sink(self):
        """Test TraceEmitter collects events."""
        from praisonaiagents.trace.protocol import TraceEmitter, ListSink
        
        sink = ListSink()
        emitter = TraceEmitter(sink=sink)
        
        emitter.agent_start("researcher")
        emitter.tool_start("search", {"q": "AI"})
        emitter.tool_end("search", duration_ms=100, status="ok")
        emitter.agent_end("researcher", duration_ms=200)
        
        events = sink.get_events()
        assert len(events) == 4
        assert events[0].event_type == "agent_start"
        assert events[1].event_type == "tool_start"
        assert events[2].event_type == "tool_end"
        assert events[3].event_type == "agent_end"
    
    def test_emitter_redacts_by_default(self):
        """Test TraceEmitter redacts sensitive data by default."""
        from praisonaiagents.trace.protocol import TraceEmitter, ListSink
        
        sink = ListSink()
        emitter = TraceEmitter(sink=sink, redact=True)
        
        emitter.tool_start("api_call", {"api_key": "sk-secret", "query": "test"})
        
        events = sink.get_events()
        assert events[0].tool_args["api_key"] == "[REDACTED]"
        assert events[0].tool_args["query"] == "test"
    
    def test_emitter_disabled(self):
        """Test TraceEmitter when disabled."""
        from praisonaiagents.trace.protocol import TraceEmitter, ListSink
        
        sink = ListSink()
        emitter = TraceEmitter(sink=sink, enabled=False)
        
        emitter.agent_start("test")
        emitter.tool_start("tool", {})
        
        # No events should be emitted
        assert len(sink.get_events()) == 0
    
    def test_emitter_error_event(self):
        """Test TraceEmitter error event."""
        from praisonaiagents.trace.protocol import TraceEmitter, ListSink
        
        sink = ListSink()
        emitter = TraceEmitter(sink=sink)
        
        emitter.error("Something went wrong", tool_name="failing_tool")
        
        events = sink.get_events()
        assert len(events) == 1
        assert events[0].event_type == "error"
        assert events[0].error_message == "Something went wrong"
        assert events[0].tool_name == "failing_tool"
    
    def test_emitter_output_event(self):
        """Test TraceEmitter output event for final agent output."""
        from praisonaiagents.trace.protocol import TraceEmitter, ListSink
        
        sink = ListSink()
        emitter = TraceEmitter(sink=sink)
        
        emitter.output("The analysis shows three major trends...")
        
        events = sink.get_events()
        assert len(events) == 1
        assert events[0].event_type == "output"
        assert "three major trends" in events[0].tool_result_summary


class TestActionTraceConfig:
    """Tests for ActionTraceConfig."""
    
    def test_config_defaults(self):
        """Test ActionTraceConfig default values."""
        from praisonaiagents.trace.protocol import ActionTraceConfig
        
        config = ActionTraceConfig()
        
        assert config.enabled is True
        assert config.redact is True
        assert config.compact is False
        assert config.sink_type == "noop"
        assert config.file_path is None
    
    def test_config_custom(self):
        """Test ActionTraceConfig custom values."""
        from praisonaiagents.trace.protocol import ActionTraceConfig
        
        config = ActionTraceConfig(
            enabled=True,
            redact=False,
            compact=True,
            sink_type="jsonl",
            file_path="/tmp/trace.jsonl",
        )
        
        assert config.redact is False
        assert config.compact is True
        assert config.sink_type == "jsonl"
        assert config.file_path == "/tmp/trace.jsonl"


class TestPerformance:
    """Performance tests for trace module."""
    
    def test_noop_sink_overhead(self):
        """Test that NoOpSink has minimal overhead."""
        from praisonaiagents.trace.protocol import TraceEmitter, NoOpSink, ActionEvent
        
        emitter = TraceEmitter(sink=NoOpSink())
        
        start = time.perf_counter()
        for _ in range(10000):
            emitter.tool_start("test", {"arg": "value"})
            emitter.tool_end("test", duration_ms=1, status="ok")
        elapsed = time.perf_counter() - start
        
        # Should complete 10000 iterations in under 100ms
        assert elapsed < 0.1, f"NoOpSink too slow: {elapsed:.3f}s for 10000 iterations"
    
    def test_disabled_emitter_overhead(self):
        """Test that disabled emitter has near-zero overhead."""
        from praisonaiagents.trace.protocol import TraceEmitter, ListSink
        
        emitter = TraceEmitter(sink=ListSink(), enabled=False)
        
        start = time.perf_counter()
        for _ in range(10000):
            emitter.tool_start("test", {"arg": "value"})
        elapsed = time.perf_counter() - start
        
        # Should complete 10000 iterations in under 500ms (very conservative)
        assert elapsed < 0.5, f"Disabled emitter too slow: {elapsed:.3f}s"
