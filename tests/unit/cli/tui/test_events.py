"""Tests for TUI Events."""

import time
from praisonai.cli.features.tui.events import TUIEvent, TUIEventType


class TestTUIEventType:
    """Tests for TUIEventType enum."""
    
    def test_event_types_exist(self):
        """Test all expected event types exist."""
        assert TUIEventType.MESSAGE_SUBMITTED
        assert TUIEventType.RUN_QUEUED
        assert TUIEventType.RUN_STARTED
        assert TUIEventType.RUN_COMPLETED
        assert TUIEventType.OUTPUT_CHUNK
        assert TUIEventType.TOOL_CALL_STARTED
        assert TUIEventType.ERROR_OCCURRED


class TestTUIEvent:
    """Tests for TUIEvent dataclass."""
    
    def test_basic_creation(self):
        """Test basic event creation."""
        event = TUIEvent(
            event_type=TUIEventType.MESSAGE_SUBMITTED,
        )
        assert event.event_type == TUIEventType.MESSAGE_SUBMITTED
        assert event.timestamp > 0
        assert event.data == {}
    
    def test_with_data(self):
        """Test event with data."""
        event = TUIEvent(
            event_type=TUIEventType.RUN_COMPLETED,
            run_id="test123",
            data={"output": "Hello"},
        )
        assert event.run_id == "test123"
        assert event.data["output"] == "Hello"
    
    def test_message_submitted_factory(self):
        """Test message_submitted factory method."""
        event = TUIEvent.message_submitted("Hello world")
        assert event.event_type == TUIEventType.MESSAGE_SUBMITTED
        assert event.data["content"] == "Hello world"
    
    def test_output_chunk_factory(self):
        """Test output_chunk factory method."""
        event = TUIEvent.output_chunk("run123", "chunk content")
        assert event.event_type == TUIEventType.OUTPUT_CHUNK
        assert event.run_id == "run123"
        assert event.data["content"] == "chunk content"
    
    def test_run_completed_factory(self):
        """Test run_completed factory method."""
        event = TUIEvent.run_completed("run123", "final output")
        assert event.event_type == TUIEventType.RUN_COMPLETED
        assert event.run_id == "run123"
        assert event.data["output"] == "final output"
    
    def test_error_factory(self):
        """Test error factory method."""
        event = TUIEvent.error("Something went wrong")
        assert event.event_type == TUIEventType.ERROR_OCCURRED
        assert event.data["message"] == "Something went wrong"
    
    def test_status_update_factory(self):
        """Test status_update factory method."""
        event = TUIEvent.status_update("Processing...")
        assert event.event_type == TUIEventType.STATUS_UPDATED
        assert event.data["status"] == "Processing..."
