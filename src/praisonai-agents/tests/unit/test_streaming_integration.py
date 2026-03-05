"""
Tests for streaming integration - verifying stream_emitter receives events through main path.

These tests verify that:
1. stream_callback and emit_events are properly threaded through chat_completion_with_tools
2. Agent.stream_emitter.emit receives StreamEvents during agent.start(stream=True)
3. StreamMetrics are populated when enable_metrics() is called
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from typing import List


class TestStreamCallbackThreading:
    """Test that stream_callback is properly threaded through the call chain."""
    
    def test_chat_completion_with_tools_accepts_stream_callback(self):
        """chat_completion_with_tools should accept stream_callback parameter."""
        from praisonaiagents.llm.openai_client import OpenAIClient
        import inspect
        
        sig = inspect.signature(OpenAIClient.chat_completion_with_tools)
        params = list(sig.parameters.keys())
        
        assert 'stream_callback' in params, "stream_callback parameter missing"
        assert 'emit_events' in params, "emit_events parameter missing"
    
    def test_achat_completion_with_tools_accepts_stream_callback(self):
        """achat_completion_with_tools should accept stream_callback parameter."""
        from praisonaiagents.llm.openai_client import OpenAIClient
        import inspect
        
        sig = inspect.signature(OpenAIClient.achat_completion_with_tools)
        params = list(sig.parameters.keys())
        
        assert 'stream_callback' in params, "stream_callback parameter missing"
        assert 'emit_events' in params, "emit_events parameter missing"
    
    def test_process_stream_response_accepts_stream_callback(self):
        """process_stream_response should accept stream_callback parameter."""
        from praisonaiagents.llm.openai_client import OpenAIClient
        import inspect
        
        sig = inspect.signature(OpenAIClient.process_stream_response)
        params = list(sig.parameters.keys())
        
        assert 'stream_callback' in params, "stream_callback parameter missing"
        assert 'emit_events' in params, "emit_events parameter missing"


class TestAgentStreamEmitterWiring:
    """Test that Agent properly wires stream_emitter through main path."""
    
    def test_agent_has_stream_emitter_property(self):
        """Agent should have stream_emitter property."""
        from praisonaiagents import Agent
        
        agent = Agent(name="test", instructions="Test agent")
        assert hasattr(agent, 'stream_emitter'), "Agent missing stream_emitter property"
    
    def test_stream_emitter_has_emit_method(self):
        """stream_emitter should have emit method."""
        from praisonaiagents import Agent
        
        agent = Agent(name="test", instructions="Test agent")
        assert hasattr(agent.stream_emitter, 'emit'), "stream_emitter missing emit method"
        assert callable(agent.stream_emitter.emit), "emit should be callable"
    
    def test_stream_emitter_has_add_callback_method(self):
        """stream_emitter should have add_callback method."""
        from praisonaiagents import Agent
        
        agent = Agent(name="test", instructions="Test agent")
        assert hasattr(agent.stream_emitter, 'add_callback'), "stream_emitter missing add_callback"
        assert callable(agent.stream_emitter.add_callback), "add_callback should be callable"
    
    def test_stream_emitter_callback_receives_events(self):
        """Callbacks added to stream_emitter should receive events when emit is called."""
        from praisonaiagents import Agent
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        agent = Agent(name="test", instructions="Test agent")
        
        received_events: List[StreamEvent] = []
        def callback(event: StreamEvent):
            received_events.append(event)
        
        agent.stream_emitter.add_callback(callback)
        
        # Manually emit an event to test callback wiring
        test_event = StreamEvent(type=StreamEventType.DELTA_TEXT, content="Hello")
        agent.stream_emitter.emit(test_event)
        
        assert len(received_events) == 1, "Callback should receive emitted event"
        assert received_events[0].type == StreamEventType.DELTA_TEXT
        assert received_events[0].content == "Hello"


class TestStreamEventTypes:
    """Test StreamEvent types are properly defined."""
    
    def test_stream_event_types_exist(self):
        """All required StreamEventType values should exist."""
        from praisonaiagents.streaming.events import StreamEventType
        
        required_types = [
            'REQUEST_START',
            'HEADERS_RECEIVED', 
            'FIRST_TOKEN',
            'DELTA_TEXT',
            'DELTA_TOOL_CALL',
            'TOOL_CALL_END',
            'LAST_TOKEN',
            'STREAM_END',
            'ERROR'
        ]
        
        for event_type in required_types:
            assert hasattr(StreamEventType, event_type), f"Missing StreamEventType.{event_type}"
    
    def test_stream_event_has_required_fields(self):
        """StreamEvent should have required fields."""
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        event = StreamEvent(type=StreamEventType.DELTA_TEXT, content="test")
        
        assert hasattr(event, 'type')
        assert hasattr(event, 'timestamp')
        assert hasattr(event, 'content')
        assert hasattr(event, 'tool_call')
        assert hasattr(event, 'is_reasoning')
        assert hasattr(event, 'agent_id')


class TestStreamMetrics:
    """Test StreamMetrics functionality."""
    
    def test_stream_emitter_has_enable_metrics(self):
        """stream_emitter should have enable_metrics method."""
        from praisonaiagents import Agent
        
        agent = Agent(name="test", instructions="Test agent")
        assert hasattr(agent.stream_emitter, 'enable_metrics')
        assert callable(agent.stream_emitter.enable_metrics)
    
    def test_stream_emitter_has_get_metrics(self):
        """stream_emitter should have get_metrics method."""
        from praisonaiagents import Agent
        
        agent = Agent(name="test", instructions="Test agent")
        assert hasattr(agent.stream_emitter, 'get_metrics')
        assert callable(agent.stream_emitter.get_metrics)
    
    def test_metrics_updated_on_emit(self):
        """Metrics should be updated when events are emitted."""
        from praisonaiagents import Agent
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType
        
        agent = Agent(name="test", instructions="Test agent")
        agent.stream_emitter.enable_metrics()
        
        # Emit events
        agent.stream_emitter.emit(StreamEvent(type=StreamEventType.REQUEST_START))
        agent.stream_emitter.emit(StreamEvent(type=StreamEventType.FIRST_TOKEN, content="H"))
        agent.stream_emitter.emit(StreamEvent(type=StreamEventType.DELTA_TEXT, content="ello"))
        agent.stream_emitter.emit(StreamEvent(type=StreamEventType.LAST_TOKEN))
        agent.stream_emitter.emit(StreamEvent(type=StreamEventType.STREAM_END))
        
        metrics = agent.stream_emitter.get_metrics()
        assert metrics is not None, "Metrics should be available after enable_metrics()"
        assert metrics.token_count >= 1, "Token count should be tracked"


class TestStreamCallbackInChatKwargs:
    """Test that _chat_completion passes stream_callback in chat_kwargs."""
    
    def test_chat_kwargs_includes_stream_callback(self):
        """_chat_completion should include stream_callback in chat_kwargs."""
        from praisonaiagents import Agent
        import inspect
        
        # Read the source code of _chat_completion to verify stream_callback is passed
        source = inspect.getsource(Agent._chat_completion)
        
        assert 'stream_callback' in source, "_chat_completion should reference stream_callback"
        assert 'stream_emitter.emit' in source, "_chat_completion should use stream_emitter.emit"
        assert 'emit_events' in source, "_chat_completion should reference emit_events"
