"""
Test AG-UI Types - TDD Tests for Event and Message Types

Phase 2: Core Types Tests
- Test EventType enum values
- Test BaseEvent creation
- Test all event type classes
- Test message type classes
- Test RunAgentInput validation
"""

import json


class TestEventType:
    """Test EventType enum."""
    
    def test_event_type_text_message_start(self):
        """Test TEXT_MESSAGE_START event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.TEXT_MESSAGE_START == "TEXT_MESSAGE_START"
    
    def test_event_type_text_message_content(self):
        """Test TEXT_MESSAGE_CONTENT event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.TEXT_MESSAGE_CONTENT == "TEXT_MESSAGE_CONTENT"
    
    def test_event_type_text_message_end(self):
        """Test TEXT_MESSAGE_END event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.TEXT_MESSAGE_END == "TEXT_MESSAGE_END"
    
    def test_event_type_tool_call_start(self):
        """Test TOOL_CALL_START event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.TOOL_CALL_START == "TOOL_CALL_START"
    
    def test_event_type_tool_call_args(self):
        """Test TOOL_CALL_ARGS event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.TOOL_CALL_ARGS == "TOOL_CALL_ARGS"
    
    def test_event_type_tool_call_end(self):
        """Test TOOL_CALL_END event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.TOOL_CALL_END == "TOOL_CALL_END"
    
    def test_event_type_tool_call_result(self):
        """Test TOOL_CALL_RESULT event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.TOOL_CALL_RESULT == "TOOL_CALL_RESULT"
    
    def test_event_type_run_started(self):
        """Test RUN_STARTED event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.RUN_STARTED == "RUN_STARTED"
    
    def test_event_type_run_finished(self):
        """Test RUN_FINISHED event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.RUN_FINISHED == "RUN_FINISHED"
    
    def test_event_type_run_error(self):
        """Test RUN_ERROR event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.RUN_ERROR == "RUN_ERROR"
    
    def test_event_type_step_started(self):
        """Test STEP_STARTED event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.STEP_STARTED == "STEP_STARTED"
    
    def test_event_type_step_finished(self):
        """Test STEP_FINISHED event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.STEP_FINISHED == "STEP_FINISHED"
    
    def test_event_type_state_snapshot(self):
        """Test STATE_SNAPSHOT event type exists."""
        from praisonaiagents.ui.agui.types import EventType
        assert EventType.STATE_SNAPSHOT == "STATE_SNAPSHOT"


class TestBaseEvent:
    """Test BaseEvent class."""
    
    def test_base_event_creation(self):
        """Test BaseEvent can be created."""
        from praisonaiagents.ui.agui.types import BaseEvent, EventType
        event = BaseEvent(type=EventType.RUN_STARTED)
        assert event.type == EventType.RUN_STARTED
    
    def test_base_event_timestamp_optional(self):
        """Test BaseEvent timestamp is optional."""
        from praisonaiagents.ui.agui.types import BaseEvent, EventType
        event = BaseEvent(type=EventType.RUN_STARTED)
        assert event.timestamp is None
    
    def test_base_event_to_dict(self):
        """Test BaseEvent can be converted to dict."""
        from praisonaiagents.ui.agui.types import BaseEvent, EventType
        event = BaseEvent(type=EventType.RUN_STARTED)
        data = event.model_dump()
        assert data["type"] == "RUN_STARTED"


class TestTextMessageEvents:
    """Test text message event classes."""
    
    def test_text_message_start_event(self):
        """Test TextMessageStartEvent creation."""
        from praisonaiagents.ui.agui.types import TextMessageStartEvent
        event = TextMessageStartEvent(message_id="msg-123", role="assistant")
        assert event.message_id == "msg-123"
        assert event.role == "assistant"
        assert event.type == "TEXT_MESSAGE_START"
    
    def test_text_message_content_event(self):
        """Test TextMessageContentEvent creation."""
        from praisonaiagents.ui.agui.types import TextMessageContentEvent
        event = TextMessageContentEvent(message_id="msg-123", delta="Hello")
        assert event.message_id == "msg-123"
        assert event.delta == "Hello"
        assert event.type == "TEXT_MESSAGE_CONTENT"
    
    def test_text_message_end_event(self):
        """Test TextMessageEndEvent creation."""
        from praisonaiagents.ui.agui.types import TextMessageEndEvent
        event = TextMessageEndEvent(message_id="msg-123")
        assert event.message_id == "msg-123"
        assert event.type == "TEXT_MESSAGE_END"


class TestToolCallEvents:
    """Test tool call event classes."""
    
    def test_tool_call_start_event(self):
        """Test ToolCallStartEvent creation."""
        from praisonaiagents.ui.agui.types import ToolCallStartEvent
        event = ToolCallStartEvent(
            tool_call_id="tc-123",
            tool_call_name="search",
            parent_message_id="msg-123"
        )
        assert event.tool_call_id == "tc-123"
        assert event.tool_call_name == "search"
        assert event.parent_message_id == "msg-123"
        assert event.type == "TOOL_CALL_START"
    
    def test_tool_call_args_event(self):
        """Test ToolCallArgsEvent creation."""
        from praisonaiagents.ui.agui.types import ToolCallArgsEvent
        event = ToolCallArgsEvent(tool_call_id="tc-123", delta='{"query": "test"}')
        assert event.tool_call_id == "tc-123"
        assert event.delta == '{"query": "test"}'
        assert event.type == "TOOL_CALL_ARGS"
    
    def test_tool_call_end_event(self):
        """Test ToolCallEndEvent creation."""
        from praisonaiagents.ui.agui.types import ToolCallEndEvent
        event = ToolCallEndEvent(tool_call_id="tc-123")
        assert event.tool_call_id == "tc-123"
        assert event.type == "TOOL_CALL_END"
    
    def test_tool_call_result_event(self):
        """Test ToolCallResultEvent creation."""
        from praisonaiagents.ui.agui.types import ToolCallResultEvent
        event = ToolCallResultEvent(
            message_id="msg-456",
            tool_call_id="tc-123",
            content="Search results..."
        )
        assert event.message_id == "msg-456"
        assert event.tool_call_id == "tc-123"
        assert event.content == "Search results..."
        assert event.type == "TOOL_CALL_RESULT"


class TestRunEvents:
    """Test run lifecycle event classes."""
    
    def test_run_started_event(self):
        """Test RunStartedEvent creation."""
        from praisonaiagents.ui.agui.types import RunStartedEvent
        event = RunStartedEvent(thread_id="thread-123", run_id="run-456")
        assert event.thread_id == "thread-123"
        assert event.run_id == "run-456"
        assert event.type == "RUN_STARTED"
    
    def test_run_finished_event(self):
        """Test RunFinishedEvent creation."""
        from praisonaiagents.ui.agui.types import RunFinishedEvent
        event = RunFinishedEvent(thread_id="thread-123", run_id="run-456")
        assert event.thread_id == "thread-123"
        assert event.run_id == "run-456"
        assert event.type == "RUN_FINISHED"
    
    def test_run_error_event(self):
        """Test RunErrorEvent creation."""
        from praisonaiagents.ui.agui.types import RunErrorEvent
        event = RunErrorEvent(message="Something went wrong")
        assert event.message == "Something went wrong"
        assert event.type == "RUN_ERROR"


class TestStepEvents:
    """Test step event classes."""
    
    def test_step_started_event(self):
        """Test StepStartedEvent creation."""
        from praisonaiagents.ui.agui.types import StepStartedEvent
        event = StepStartedEvent(step_name="research")
        assert event.step_name == "research"
        assert event.type == "STEP_STARTED"
    
    def test_step_finished_event(self):
        """Test StepFinishedEvent creation."""
        from praisonaiagents.ui.agui.types import StepFinishedEvent
        event = StepFinishedEvent(step_name="research")
        assert event.step_name == "research"
        assert event.type == "STEP_FINISHED"


class TestStateEvents:
    """Test state event classes."""
    
    def test_state_snapshot_event(self):
        """Test StateSnapshotEvent creation."""
        from praisonaiagents.ui.agui.types import StateSnapshotEvent
        event = StateSnapshotEvent(snapshot={"key": "value"})
        assert event.snapshot == {"key": "value"}
        assert event.type == "STATE_SNAPSHOT"


class TestMessageTypes:
    """Test message type classes."""
    
    def test_user_message(self):
        """Test UserMessage creation."""
        from praisonaiagents.ui.agui.types import Message
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
    
    def test_assistant_message(self):
        """Test AssistantMessage creation."""
        from praisonaiagents.ui.agui.types import Message
        msg = Message(role="assistant", content="Hi there!")
        assert msg.role == "assistant"
        assert msg.content == "Hi there!"
    
    def test_tool_message(self):
        """Test ToolMessage creation."""
        from praisonaiagents.ui.agui.types import Message
        msg = Message(role="tool", content="Result", tool_call_id="tc-123")
        assert msg.role == "tool"
        assert msg.content == "Result"
        assert msg.tool_call_id == "tc-123"


class TestToolCall:
    """Test ToolCall type."""
    
    def test_tool_call_creation(self):
        """Test ToolCall creation."""
        from praisonaiagents.ui.agui.types import ToolCall, FunctionCall
        tc = ToolCall(
            id="tc-123",
            function=FunctionCall(name="search", arguments='{"query": "test"}')
        )
        assert tc.id == "tc-123"
        assert tc.function.name == "search"
        assert tc.function.arguments == '{"query": "test"}'


class TestRunAgentInput:
    """Test RunAgentInput type."""
    
    def test_run_agent_input_creation(self):
        """Test RunAgentInput creation."""
        from praisonaiagents.ui.agui.types import RunAgentInput, Message
        input_data = RunAgentInput(
            thread_id="thread-123",
            run_id="run-456",
            messages=[Message(role="user", content="Hello")]
        )
        assert input_data.thread_id == "thread-123"
        assert input_data.run_id == "run-456"
        assert len(input_data.messages) == 1
    
    def test_run_agent_input_optional_fields(self):
        """Test RunAgentInput optional fields."""
        from praisonaiagents.ui.agui.types import RunAgentInput
        input_data = RunAgentInput(thread_id="thread-123")
        assert input_data.thread_id == "thread-123"
        assert input_data.run_id is None
        assert input_data.messages is None or len(input_data.messages) == 0
        assert input_data.state is None


class TestEventSerialization:
    """Test event serialization to JSON."""
    
    def test_event_json_serialization(self):
        """Test events can be serialized to JSON."""
        from praisonaiagents.ui.agui.types import TextMessageStartEvent
        event = TextMessageStartEvent(message_id="msg-123", role="assistant")
        json_str = event.model_dump_json()
        data = json.loads(json_str)
        assert data["type"] == "TEXT_MESSAGE_START"
        assert data["message_id"] == "msg-123"
    
    def test_event_sse_format(self):
        """Test events can be formatted as SSE."""
        from praisonaiagents.ui.agui.types import TextMessageStartEvent
        from praisonaiagents.ui.agui.encoder import EventEncoder
        
        encoder = EventEncoder()
        event = TextMessageStartEvent(message_id="msg-123", role="assistant")
        sse = encoder.encode(event)
        
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        # Parse the JSON part
        json_part = sse[6:-2]  # Remove "data: " prefix and "\n\n" suffix
        data = json.loads(json_part)
        assert data["type"] == "TEXT_MESSAGE_START"
