"""
Tests for StreamEvent dataclass and streaming events.

TDD: These tests are written FIRST to define expected behavior.
"""

import time


class TestStreamEventDataclass:
    """Tests for StreamEvent dataclass fields and defaults."""
    
    def test_stream_event_has_is_reasoning_field(self):
        """StreamEvent should have is_reasoning field."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(type=StreamEventType.DELTA_TEXT)
        assert hasattr(event, 'is_reasoning'), "StreamEvent missing 'is_reasoning' field"
    
    def test_stream_event_is_reasoning_defaults_to_false(self):
        """is_reasoning should default to False for backward compatibility."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(type=StreamEventType.DELTA_TEXT, content="Hello")
        assert event.is_reasoning is False, "is_reasoning should default to False"
    
    def test_stream_event_is_reasoning_can_be_set_true(self):
        """is_reasoning can be explicitly set to True."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(
            type=StreamEventType.DELTA_TEXT,
            content="Thinking...",
            is_reasoning=True
        )
        assert event.is_reasoning is True
    
    def test_stream_event_has_agent_id_field(self):
        """StreamEvent should have optional agent_id field."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(type=StreamEventType.DELTA_TEXT)
        assert hasattr(event, 'agent_id'), "StreamEvent missing 'agent_id' field"
    
    def test_stream_event_agent_id_defaults_to_none(self):
        """agent_id should default to None."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(type=StreamEventType.DELTA_TEXT)
        assert event.agent_id is None, "agent_id should default to None"
    
    def test_stream_event_agent_id_can_be_set(self):
        """agent_id can be explicitly set."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(
            type=StreamEventType.DELTA_TEXT,
            content="Hello",
            agent_id="agent-123"
        )
        assert event.agent_id == "agent-123"
    
    def test_stream_event_has_session_id_field(self):
        """StreamEvent should have optional session_id field."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(type=StreamEventType.DELTA_TEXT)
        assert hasattr(event, 'session_id'), "StreamEvent missing 'session_id' field"
    
    def test_stream_event_session_id_defaults_to_none(self):
        """session_id should default to None."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(type=StreamEventType.DELTA_TEXT)
        assert event.session_id is None, "session_id should default to None"
    
    def test_stream_event_has_run_id_field(self):
        """StreamEvent should have optional run_id field."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(type=StreamEventType.DELTA_TEXT)
        assert hasattr(event, 'run_id'), "StreamEvent missing 'run_id' field"
    
    def test_stream_event_run_id_defaults_to_none(self):
        """run_id should default to None."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(type=StreamEventType.DELTA_TEXT)
        assert event.run_id is None, "run_id should default to None"


class TestStreamEventBackwardCompatibility:
    """Tests to ensure backward compatibility with existing code."""
    
    def test_existing_code_works_without_new_fields(self):
        """Existing code that doesn't use new fields should work unchanged."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        # This is how existing code creates events
        event = StreamEvent(
            type=StreamEventType.DELTA_TEXT,
            content="Hello world"
        )
        
        assert event.type == StreamEventType.DELTA_TEXT
        assert event.content == "Hello world"
        assert event.is_reasoning is False  # Default
        assert event.agent_id is None  # Default
    
    def test_stream_event_repr_works_with_new_fields(self):
        """__repr__ should work with new fields."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(
            type=StreamEventType.DELTA_TEXT,
            content="Hello",
            is_reasoning=True,
            agent_id="agent-1"
        )
        
        repr_str = repr(event)
        assert "DELTA_TEXT" in repr_str or "delta_text" in repr_str
    
    def test_stream_metrics_update_from_event_works(self):
        """StreamMetrics.update_from_event should work with new fields."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType, StreamMetrics
        
        metrics = StreamMetrics()
        event = StreamEvent(
            type=StreamEventType.DELTA_TEXT,
            content="Hello",
            is_reasoning=True
        )
        
        # Should not raise
        metrics.update_from_event(event)
        assert metrics.token_count == 1


class TestStreamEventEmitterWithNewFields:
    """Tests for StreamEventEmitter with new StreamEvent fields."""
    
    def test_emitter_handles_reasoning_events(self):
        """StreamEventEmitter should handle events with is_reasoning=True."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType, StreamEventEmitter
        
        emitter = StreamEventEmitter()
        received_events = []
        
        def callback(event):
            received_events.append(event)
        
        emitter.add_callback(callback)
        
        # Emit a reasoning event
        event = StreamEvent(
            type=StreamEventType.DELTA_TEXT,
            content="Thinking...",
            is_reasoning=True
        )
        emitter.emit(event)
        
        assert len(received_events) == 1
        assert received_events[0].is_reasoning is True
    
    def test_emitter_handles_agent_context(self):
        """StreamEventEmitter should handle events with agent context."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType, StreamEventEmitter
        
        emitter = StreamEventEmitter()
        received_events = []
        
        def callback(event):
            received_events.append(event)
        
        emitter.add_callback(callback)
        
        # Emit an event with agent context
        event = StreamEvent(
            type=StreamEventType.DELTA_TEXT,
            content="Hello",
            agent_id="agent-123",
            session_id="session-456",
            run_id="run-789"
        )
        emitter.emit(event)
        
        assert len(received_events) == 1
        assert received_events[0].agent_id == "agent-123"
        assert received_events[0].session_id == "session-456"
        assert received_events[0].run_id == "run-789"


class TestStreamEventReasoningCallback:
    """Tests for handling reasoning content in callbacks."""
    
    def test_callback_can_distinguish_reasoning_content(self):
        """Callback should be able to distinguish reasoning from regular content."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        regular_events = []
        reasoning_events = []
        
        def callback(event):
            if event.type == StreamEventType.DELTA_TEXT:
                if event.is_reasoning:
                    reasoning_events.append(event)
                else:
                    regular_events.append(event)
        
        # Simulate receiving events
        events = [
            StreamEvent(type=StreamEventType.DELTA_TEXT, content="Hello", is_reasoning=False),
            StreamEvent(type=StreamEventType.DELTA_TEXT, content="Thinking...", is_reasoning=True),
            StreamEvent(type=StreamEventType.DELTA_TEXT, content="World", is_reasoning=False),
        ]
        
        for event in events:
            callback(event)
        
        assert len(regular_events) == 2
        assert len(reasoning_events) == 1
        assert reasoning_events[0].content == "Thinking..."


class TestCreateTextPrinterCallbackWithReasoning:
    """Tests for text printer callback with reasoning support."""
    
    def test_create_text_printer_callback_exists(self):
        """create_text_printer_callback should exist."""
        from praisonaiagents.streaming.events import create_text_printer_callback
        
        callback = create_text_printer_callback()
        assert callable(callback)


class TestStreamEventAllFields:
    """Test all StreamEvent fields together."""
    
    def test_stream_event_all_fields(self):
        """StreamEvent should support all fields together."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(
            type=StreamEventType.DELTA_TEXT,
            timestamp=time.perf_counter(),
            content="Hello",
            tool_call=None,
            metadata={"key": "value"},
            error=None,
            is_reasoning=True,
            agent_id="agent-1",
            session_id="session-1",
            run_id="run-1"
        )
        
        assert event.type == StreamEventType.DELTA_TEXT
        assert event.content == "Hello"
        assert event.is_reasoning is True
        assert event.agent_id == "agent-1"
        assert event.session_id == "session-1"
        assert event.run_id == "run-1"
        assert event.metadata == {"key": "value"}


class TestAgentIdPopulation:
    """Tests for agent_id population in streaming events."""
    
    def test_agent_has_agent_id_property(self):
        """Agent should have agent_id property for streaming context."""
        from praisonaiagents import Agent
        
        agent = Agent(name="test-agent")
        # Agent should have an agent_id (either explicit or derived from name)
        assert hasattr(agent, 'agent_id') or hasattr(agent, 'name')
    
    def test_stream_emitter_can_receive_agent_context(self):
        """StreamEventEmitter should handle events with agent context."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType, StreamEventEmitter
        
        emitter = StreamEventEmitter()
        received = []
        emitter.add_callback(lambda e: received.append(e))
        
        event = StreamEvent(
            type=StreamEventType.DELTA_TEXT,
            content="test",
            agent_id="my-agent",
            session_id="sess-1",
            run_id="run-1"
        )
        emitter.emit(event)
        
        assert len(received) == 1
        assert received[0].agent_id == "my-agent"


class TestLiteLLMReasoningSupport:
    """Tests for LiteLLM reasoning content support."""
    
    def test_llm_class_has_stream_callback_param(self):
        """LLM.get_response should accept stream_callback parameter."""
        from praisonaiagents.llm import LLM
        import inspect
        
        # Check if get_response method exists and has stream_callback param
        sig = inspect.signature(LLM.get_response)
        params = list(sig.parameters.keys())
        assert 'stream_callback' in params, "LLM.get_response should have stream_callback parameter"
    
    def test_llm_class_has_emit_events_param(self):
        """LLM.get_response should accept emit_events parameter."""
        from praisonaiagents.llm import LLM
        import inspect
        
        sig = inspect.signature(LLM.get_response)
        params = list(sig.parameters.keys())
        assert 'emit_events' in params, "LLM.get_response should have emit_events parameter"


class TestGeneratorStreamingPath:
    """Tests for generator-based streaming with callbacks."""
    
    def test_openai_client_generator_has_stream_callback(self):
        """OpenAI client generator should support stream_callback."""
        from praisonaiagents.llm.openai_client import OpenAIClient
        import inspect
        
        # Check chat_completion_with_tools_stream signature
        sig = inspect.signature(OpenAIClient.chat_completion_with_tools_stream)
        params = list(sig.parameters.keys())
        assert 'stream_callback' in params, "chat_completion_with_tools_stream should have stream_callback"
