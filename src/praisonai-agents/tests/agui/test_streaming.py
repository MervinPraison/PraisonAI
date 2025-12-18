"""
Test AG-UI Event Streaming - TDD Tests for Streaming PraisonAI Responses

Phase 4: Event Streaming Tests
- Test streaming text content as AG-UI events
- Test streaming tool calls as AG-UI events
- Test run lifecycle events (start, finish, error)
- Test step events
- Test event ordering
"""

import asyncio


class TestTextMessageStreaming:
    """Test streaming text messages."""
    
    def test_stream_simple_text(self):
        """Test streaming simple text content."""
        from praisonaiagents.ui.agui.streaming import create_text_message_events
        
        events = list(create_text_message_events(
            content="Hello, world!",
            message_id="msg-123"
        ))
        
        # Should have start, content, end events
        assert len(events) == 3
        assert events[0].type == "TEXT_MESSAGE_START"
        assert events[0].message_id == "msg-123"
        assert events[1].type == "TEXT_MESSAGE_CONTENT"
        assert events[1].delta == "Hello, world!"
        assert events[2].type == "TEXT_MESSAGE_END"
    
    def test_stream_chunked_text(self):
        """Test streaming text in chunks."""
        from praisonaiagents.ui.agui.streaming import stream_text_chunks
        
        chunks = ["Hello", ", ", "world", "!"]
        events = list(stream_text_chunks(chunks, message_id="msg-123"))
        
        # Should have start, 4 content events, end
        assert len(events) == 6
        assert events[0].type == "TEXT_MESSAGE_START"
        assert events[1].delta == "Hello"
        assert events[2].delta == ", "
        assert events[3].delta == "world"
        assert events[4].delta == "!"
        assert events[5].type == "TEXT_MESSAGE_END"
    
    def test_stream_empty_text(self):
        """Test streaming empty text."""
        from praisonaiagents.ui.agui.streaming import create_text_message_events
        
        events = list(create_text_message_events(content="", message_id="msg-123"))
        
        # Should still have start and end, but no content
        assert len(events) == 2
        assert events[0].type == "TEXT_MESSAGE_START"
        assert events[1].type == "TEXT_MESSAGE_END"


class TestToolCallStreaming:
    """Test streaming tool calls."""
    
    def test_stream_tool_call(self):
        """Test streaming a tool call."""
        from praisonaiagents.ui.agui.streaming import create_tool_call_events
        
        events = list(create_tool_call_events(
            tool_call_id="tc-123",
            tool_name="search",
            arguments='{"query": "test"}',
            parent_message_id="msg-123"
        ))
        
        # Should have start, args, end events
        assert len(events) == 3
        assert events[0].type == "TOOL_CALL_START"
        assert events[0].tool_call_id == "tc-123"
        assert events[0].tool_call_name == "search"
        assert events[1].type == "TOOL_CALL_ARGS"
        assert events[1].delta == '{"query": "test"}'
        assert events[2].type == "TOOL_CALL_END"
    
    def test_stream_tool_result(self):
        """Test streaming a tool result."""
        from praisonaiagents.ui.agui.streaming import create_tool_result_event
        
        event = create_tool_result_event(
            tool_call_id="tc-123",
            content="Search results...",
            message_id="msg-456"
        )
        
        assert event.type == "TOOL_CALL_RESULT"
        assert event.tool_call_id == "tc-123"
        assert event.content == "Search results..."


class TestRunLifecycleEvents:
    """Test run lifecycle events."""
    
    def test_create_run_started_event(self):
        """Test creating run started event."""
        from praisonaiagents.ui.agui.streaming import create_run_started_event
        
        event = create_run_started_event(thread_id="thread-123", run_id="run-456")
        
        assert event.type == "RUN_STARTED"
        assert event.thread_id == "thread-123"
        assert event.run_id == "run-456"
    
    def test_create_run_finished_event(self):
        """Test creating run finished event."""
        from praisonaiagents.ui.agui.streaming import create_run_finished_event
        
        event = create_run_finished_event(thread_id="thread-123", run_id="run-456")
        
        assert event.type == "RUN_FINISHED"
        assert event.thread_id == "thread-123"
        assert event.run_id == "run-456"
    
    def test_create_run_error_event(self):
        """Test creating run error event."""
        from praisonaiagents.ui.agui.streaming import create_run_error_event
        
        event = create_run_error_event(message="Something went wrong", code="ERR001")
        
        assert event.type == "RUN_ERROR"
        assert event.message == "Something went wrong"
        assert event.code == "ERR001"


class TestStepEvents:
    """Test step events."""
    
    def test_create_step_started_event(self):
        """Test creating step started event."""
        from praisonaiagents.ui.agui.streaming import create_step_started_event
        
        event = create_step_started_event(step_name="research")
        
        assert event.type == "STEP_STARTED"
        assert event.step_name == "research"
    
    def test_create_step_finished_event(self):
        """Test creating step finished event."""
        from praisonaiagents.ui.agui.streaming import create_step_finished_event
        
        event = create_step_finished_event(step_name="research")
        
        assert event.type == "STEP_FINISHED"
        assert event.step_name == "research"


class TestEventBuffer:
    """Test EventBuffer for managing event ordering."""
    
    def test_event_buffer_creation(self):
        """Test EventBuffer creation."""
        from praisonaiagents.ui.agui.streaming import EventBuffer
        
        buffer = EventBuffer()
        assert buffer.active_tool_call_ids == set()
        assert buffer.current_text_message_id == ""
    
    def test_event_buffer_start_tool_call(self):
        """Test starting a tool call in buffer."""
        from praisonaiagents.ui.agui.streaming import EventBuffer
        
        buffer = EventBuffer()
        buffer.start_tool_call("tc-123")
        
        assert "tc-123" in buffer.active_tool_call_ids
    
    def test_event_buffer_end_tool_call(self):
        """Test ending a tool call in buffer."""
        from praisonaiagents.ui.agui.streaming import EventBuffer
        
        buffer = EventBuffer()
        buffer.start_tool_call("tc-123")
        buffer.end_tool_call("tc-123")
        
        assert "tc-123" not in buffer.active_tool_call_ids
        assert "tc-123" in buffer.ended_tool_call_ids
    
    def test_event_buffer_start_text_message(self):
        """Test starting a text message in buffer."""
        from praisonaiagents.ui.agui.streaming import EventBuffer
        
        buffer = EventBuffer()
        msg_id = buffer.start_text_message()
        
        assert msg_id != ""
        assert buffer.current_text_message_id == msg_id


class TestAsyncStreaming:
    """Test async streaming functionality."""
    
    def test_async_stream_response(self):
        """Test async streaming of agent response."""
        async def run_test():
            from praisonaiagents.ui.agui.streaming import async_stream_response
            
            # Mock response chunks
            async def mock_chunks():
                yield "Hello"
                yield ", "
                yield "world!"
            
            events = []
            async for event in async_stream_response(
                response_stream=mock_chunks(),
                thread_id="thread-123",
                run_id="run-456"
            ):
                events.append(event)
            
            # Should have run_started, text events, run_finished
            assert len(events) > 0
            assert events[0].type == "RUN_STARTED"
            assert events[-1].type == "RUN_FINISHED"
        
        asyncio.run(run_test())


class TestStateSnapshotEvents:
    """Test state snapshot events."""
    
    def test_create_state_snapshot_event(self):
        """Test creating state snapshot event."""
        from praisonaiagents.ui.agui.streaming import create_state_snapshot_event
        
        state = {"task": "research", "progress": 50}
        event = create_state_snapshot_event(state)
        
        assert event.type == "STATE_SNAPSHOT"
        assert event.snapshot == state
