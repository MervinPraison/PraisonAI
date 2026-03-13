"""
TDD tests for TOOL_CALL_START and TOOL_CALL_RESULT stream events.

These events provide complete parsed arguments (dict) for tool calls,
enabling consumers like AIUI to display keyword-rich descriptions.
"""



class TestStreamEventTypeEnumValues:
    """Test that new StreamEventType values exist."""
    
    def test_tool_call_start_event_type_exists(self):
        """Verify TOOL_CALL_START enum value exists."""
        from praisonaiagents.streaming.events import StreamEventType
        assert hasattr(StreamEventType, 'TOOL_CALL_START')
        assert StreamEventType.TOOL_CALL_START.value == "tool_call_start"
    
    def test_tool_call_result_event_type_exists(self):
        """Verify TOOL_CALL_RESULT enum value exists."""
        from praisonaiagents.streaming.events import StreamEventType
        assert hasattr(StreamEventType, 'TOOL_CALL_RESULT')
        assert StreamEventType.TOOL_CALL_RESULT.value == "tool_call_result"
    
    def test_existing_events_unchanged(self):
        """Verify existing event types are unchanged for backward compat."""
        from praisonaiagents.streaming.events import StreamEventType
        assert StreamEventType.DELTA_TOOL_CALL.value == "delta_tool_call"
        assert StreamEventType.TOOL_CALL_END.value == "tool_call_end"
        assert StreamEventType.REQUEST_START.value == "request_start"
        assert StreamEventType.STREAM_END.value == "stream_end"


class TestStreamEventCreation:
    """Test creating StreamEvent with new types."""
    
    def test_create_tool_call_start_event(self):
        """Verify TOOL_CALL_START event can be created with parsed args dict."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(
            type=StreamEventType.TOOL_CALL_START,
            tool_call={
                "name": "search_web",
                "arguments": {"query": "Django tutorials"},  # Parsed dict, NOT JSON string
                "id": "call_abc123",
            },
            agent_id="test_agent",
        )
        
        assert event.type == StreamEventType.TOOL_CALL_START
        assert event.tool_call["name"] == "search_web"
        assert isinstance(event.tool_call["arguments"], dict)
        assert event.tool_call["arguments"]["query"] == "Django tutorials"
        assert event.agent_id == "test_agent"
    
    def test_create_tool_call_result_event(self):
        """Verify TOOL_CALL_RESULT event can be created with result."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(
            type=StreamEventType.TOOL_CALL_RESULT,
            tool_call={
                "name": "search_web",
                "arguments": {"query": "Django tutorials"},
                "result": "Found 10 results for Django tutorials",
                "id": "call_abc123",
            },
            agent_id="test_agent",
            metadata={"duration_ms": 150.5},
        )
        
        assert event.type == StreamEventType.TOOL_CALL_RESULT
        assert event.tool_call["result"] == "Found 10 results for Django tutorials"
        assert event.metadata["duration_ms"] == 150.5


class TestStreamEventEmitterWithNewEvents:
    """Test StreamEventEmitter emits new event types correctly."""
    
    def test_emitter_emits_tool_call_start(self):
        """Verify emitter can emit TOOL_CALL_START events."""
        from praisonaiagents.streaming.events import (
            StreamEventEmitter, StreamEvent, StreamEventType
        )
        
        emitter = StreamEventEmitter()
        received_events = []
        
        def callback(event):
            received_events.append(event)
        
        emitter.add_callback(callback)
        
        event = StreamEvent(
            type=StreamEventType.TOOL_CALL_START,
            tool_call={
                "name": "read_file",
                "arguments": {"filepath": "/tmp/test.txt"},
                "id": "call_xyz789",
            },
        )
        emitter.emit(event)
        
        assert len(received_events) == 1
        assert received_events[0].type == StreamEventType.TOOL_CALL_START
        assert received_events[0].tool_call["arguments"]["filepath"] == "/tmp/test.txt"
    
    def test_emitter_emits_tool_call_result(self):
        """Verify emitter can emit TOOL_CALL_RESULT events."""
        from praisonaiagents.streaming.events import (
            StreamEventEmitter, StreamEvent, StreamEventType
        )
        
        emitter = StreamEventEmitter()
        received_events = []
        
        def callback(event):
            received_events.append(event)
        
        emitter.add_callback(callback)
        
        event = StreamEvent(
            type=StreamEventType.TOOL_CALL_RESULT,
            tool_call={
                "name": "read_file",
                "arguments": {"filepath": "/tmp/test.txt"},
                "result": "File contents here...",
                "id": "call_xyz789",
            },
        )
        emitter.emit(event)
        
        assert len(received_events) == 1
        assert received_events[0].type == StreamEventType.TOOL_CALL_RESULT
        assert received_events[0].tool_call["result"] == "File contents here..."
    
    def test_no_callbacks_no_overhead(self):
        """Verify no overhead when no callbacks registered."""
        from praisonaiagents.streaming.events import (
            StreamEventEmitter, StreamEvent, StreamEventType
        )
        
        emitter = StreamEventEmitter()
        assert not emitter.has_callbacks
        
        # Should not raise, just no-op
        event = StreamEvent(
            type=StreamEventType.TOOL_CALL_START,
            tool_call={"name": "test", "arguments": {}},
        )
        emitter.emit(event)  # No error, no callbacks called


class TestToolCallEventSemantics:
    """Test the semantic differences between tool call event types."""
    
    def test_delta_vs_start_event_args_type(self):
        """
        DELTA_TOOL_CALL has partial JSON string args.
        TOOL_CALL_START has complete parsed dict args.
        """
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        # DELTA_TOOL_CALL - partial JSON string (as received from LLM streaming)
        delta_event = StreamEvent(
            type=StreamEventType.DELTA_TOOL_CALL,
            tool_call={
                "name": "search_web",
                "arguments": '{"qu',  # Partial JSON string
                "id": "call_123",
            },
        )
        
        # TOOL_CALL_START - complete parsed dict (at execution time)
        start_event = StreamEvent(
            type=StreamEventType.TOOL_CALL_START,
            tool_call={
                "name": "search_web",
                "arguments": {"query": "Django"},  # Complete parsed dict
                "id": "call_123",
            },
        )
        
        # Delta has string args
        assert isinstance(delta_event.tool_call["arguments"], str)
        
        # Start has dict args
        assert isinstance(start_event.tool_call["arguments"], dict)
        assert "query" in start_event.tool_call["arguments"]


class TestToolCallIdPropagation:
    """Test that tool_call_id is properly threaded through execute_tool."""
    
    def test_execute_tool_accepts_tool_call_id(self):
        """Verify execute_tool() accepts tool_call_id parameter."""
        from praisonaiagents import Agent
        import inspect
        
        sig = inspect.signature(Agent.execute_tool)
        params = list(sig.parameters.keys())
        assert 'tool_call_id' in params, "execute_tool should accept tool_call_id parameter"
    
    def test_execute_tool_with_context_accepts_tool_call_id(self):
        """Verify _execute_tool_with_context() accepts tool_call_id parameter."""
        from praisonaiagents import Agent
        import inspect
        
        sig = inspect.signature(Agent._execute_tool_with_context)
        params = list(sig.parameters.keys())
        assert 'tool_call_id' in params, "_execute_tool_with_context should accept tool_call_id parameter"
    
    def test_tool_call_id_in_stream_event(self):
        """Verify tool_call_id can be included in StreamEvent."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(
            type=StreamEventType.TOOL_CALL_START,
            tool_call={
                "name": "test_tool",
                "arguments": {"arg": "value"},
                "id": "call_abc123xyz",  # The tool_call_id
            },
        )
        
        assert event.tool_call["id"] == "call_abc123xyz"
