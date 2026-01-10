"""
Unit tests for streaming events module.

Tests cover:
- StreamEvent creation and representation
- StreamEventType enum values
- StreamMetrics calculations (TTFT, stream duration, total time)
- StreamEventEmitter callback management
- create_text_printer_callback and create_metrics_callback helpers
"""

import time
from praisonaiagents.streaming.events import (
    StreamEvent,
    StreamEventType,
    StreamMetrics,
    StreamEventEmitter,
    create_text_printer_callback,
    create_metrics_callback,
)


class TestStreamEventType:
    """Tests for StreamEventType enum."""
    
    def test_event_types_exist(self):
        """All required event types should exist."""
        assert StreamEventType.REQUEST_START.value == "request_start"
        assert StreamEventType.HEADERS_RECEIVED.value == "headers_received"
        assert StreamEventType.FIRST_TOKEN.value == "first_token"
        assert StreamEventType.DELTA_TEXT.value == "delta_text"
        assert StreamEventType.DELTA_TOOL_CALL.value == "delta_tool_call"
        assert StreamEventType.TOOL_CALL_END.value == "tool_call_end"
        assert StreamEventType.LAST_TOKEN.value == "last_token"
        assert StreamEventType.STREAM_END.value == "stream_end"
        assert StreamEventType.ERROR.value == "error"


class TestStreamEvent:
    """Tests for StreamEvent dataclass."""
    
    def test_create_basic_event(self):
        """Create a basic event with type only."""
        event = StreamEvent(type=StreamEventType.REQUEST_START)
        assert event.type == StreamEventType.REQUEST_START
        assert event.timestamp > 0
        assert event.content is None
        assert event.tool_call is None
        assert event.metadata is None
        assert event.error is None
    
    def test_create_event_with_content(self):
        """Create an event with content."""
        event = StreamEvent(
            type=StreamEventType.DELTA_TEXT,
            content="Hello"
        )
        assert event.type == StreamEventType.DELTA_TEXT
        assert event.content == "Hello"
    
    def test_create_event_with_tool_call(self):
        """Create an event with tool call data."""
        tool_data = {"name": "calculator", "arguments": '{"x": 1}'}
        event = StreamEvent(
            type=StreamEventType.DELTA_TOOL_CALL,
            tool_call=tool_data
        )
        assert event.type == StreamEventType.DELTA_TOOL_CALL
        assert event.tool_call == tool_data
    
    def test_create_event_with_metadata(self):
        """Create an event with metadata."""
        event = StreamEvent(
            type=StreamEventType.REQUEST_START,
            metadata={"model": "gpt-4o-mini", "message_count": 2}
        )
        assert event.metadata["model"] == "gpt-4o-mini"
        assert event.metadata["message_count"] == 2
    
    def test_create_error_event(self):
        """Create an error event."""
        event = StreamEvent(
            type=StreamEventType.ERROR,
            error="Connection timeout"
        )
        assert event.type == StreamEventType.ERROR
        assert event.error == "Connection timeout"
    
    def test_event_repr(self):
        """Event repr should be informative."""
        event = StreamEvent(
            type=StreamEventType.DELTA_TEXT,
            content="Hello world"
        )
        repr_str = repr(event)
        assert "DELTA_TEXT" in repr_str or "delta_text" in repr_str
        assert "Hello world" in repr_str


class TestStreamMetrics:
    """Tests for StreamMetrics dataclass."""
    
    def test_default_metrics(self):
        """Default metrics should be zero."""
        metrics = StreamMetrics()
        assert metrics.request_start == 0.0
        assert metrics.headers_received == 0.0
        assert metrics.first_token == 0.0
        assert metrics.last_token == 0.0
        assert metrics.stream_end == 0.0
        assert metrics.token_count == 0
    
    def test_ttft_calculation(self):
        """TTFT should be first_token - request_start."""
        metrics = StreamMetrics()
        metrics.request_start = 100.0
        metrics.first_token = 100.5
        assert metrics.ttft == 0.5
    
    def test_ttft_zero_when_no_first_token(self):
        """TTFT should be 0 when first_token not set."""
        metrics = StreamMetrics()
        metrics.request_start = 100.0
        assert metrics.ttft == 0.0
    
    def test_stream_duration_calculation(self):
        """Stream duration should be last_token - first_token."""
        metrics = StreamMetrics()
        metrics.first_token = 100.0
        metrics.last_token = 102.0
        assert metrics.stream_duration == 2.0
    
    def test_total_time_calculation(self):
        """Total time should be stream_end - request_start."""
        metrics = StreamMetrics()
        metrics.request_start = 100.0
        metrics.stream_end = 103.0
        assert metrics.total_time == 3.0
    
    def test_tokens_per_second(self):
        """Tokens per second calculation."""
        metrics = StreamMetrics()
        metrics.first_token = 100.0
        metrics.last_token = 102.0  # 2 second duration
        metrics.token_count = 100
        assert metrics.tokens_per_second == 50.0
    
    def test_tokens_per_second_zero_duration(self):
        """Tokens per second should be 0 when duration is 0."""
        metrics = StreamMetrics()
        assert metrics.tokens_per_second == 0.0
    
    def test_update_from_event(self):
        """Metrics should update from events."""
        metrics = StreamMetrics()
        
        # Request start
        event1 = StreamEvent(type=StreamEventType.REQUEST_START, timestamp=100.0)
        metrics.update_from_event(event1)
        assert metrics.request_start == 100.0
        
        # Headers received
        event2 = StreamEvent(type=StreamEventType.HEADERS_RECEIVED, timestamp=100.2)
        metrics.update_from_event(event2)
        assert metrics.headers_received == 100.2
        
        # First token
        event3 = StreamEvent(type=StreamEventType.FIRST_TOKEN, timestamp=100.5)
        metrics.update_from_event(event3)
        assert metrics.first_token == 100.5
        assert metrics.token_count == 1
        
        # Delta text
        event4 = StreamEvent(type=StreamEventType.DELTA_TEXT, timestamp=100.6)
        metrics.update_from_event(event4)
        assert metrics.token_count == 2
        
        # Last token
        event5 = StreamEvent(type=StreamEventType.LAST_TOKEN, timestamp=102.0)
        metrics.update_from_event(event5)
        assert metrics.last_token == 102.0
        
        # Stream end
        event6 = StreamEvent(type=StreamEventType.STREAM_END, timestamp=102.1)
        metrics.update_from_event(event6)
        assert metrics.stream_end == 102.1
    
    def test_to_dict(self):
        """Metrics should convert to dict."""
        metrics = StreamMetrics()
        metrics.request_start = 100.0
        metrics.first_token = 100.5
        metrics.last_token = 102.0
        metrics.stream_end = 102.1
        metrics.token_count = 50
        
        d = metrics.to_dict()
        assert "ttft_ms" in d
        assert "stream_duration_ms" in d
        assert "total_time_ms" in d
        assert "token_count" in d
        assert "tokens_per_second" in d
    
    def test_format_summary(self):
        """Metrics should format as summary string."""
        metrics = StreamMetrics()
        metrics.request_start = 100.0
        metrics.first_token = 100.5
        metrics.last_token = 102.0
        metrics.stream_end = 102.1
        metrics.token_count = 50
        
        summary = metrics.format_summary()
        assert "TTFT" in summary
        assert "Stream" in summary
        assert "Total" in summary
        assert "Tokens" in summary


class TestStreamEventEmitter:
    """Tests for StreamEventEmitter."""
    
    def test_create_emitter(self):
        """Create an emitter."""
        emitter = StreamEventEmitter()
        assert not emitter.has_callbacks
    
    def test_add_callback(self):
        """Add a callback."""
        emitter = StreamEventEmitter()
        events = []
        
        def callback(event):
            events.append(event)
        
        emitter.add_callback(callback)
        assert emitter.has_callbacks
    
    def test_remove_callback(self):
        """Remove a callback."""
        emitter = StreamEventEmitter()
        events = []
        
        def callback(event):
            events.append(event)
        
        emitter.add_callback(callback)
        emitter.remove_callback(callback)
        assert not emitter.has_callbacks
    
    def test_emit_calls_callbacks(self):
        """Emit should call all callbacks."""
        emitter = StreamEventEmitter()
        events1 = []
        events2 = []
        
        emitter.add_callback(lambda e: events1.append(e))
        emitter.add_callback(lambda e: events2.append(e))
        
        event = StreamEvent(type=StreamEventType.DELTA_TEXT, content="Hello")
        emitter.emit(event)
        
        assert len(events1) == 1
        assert len(events2) == 1
        assert events1[0].content == "Hello"
    
    def test_emit_with_metrics(self):
        """Emit should update metrics when enabled."""
        emitter = StreamEventEmitter()
        emitter.enable_metrics()
        
        emitter.emit(StreamEvent(type=StreamEventType.REQUEST_START, timestamp=100.0))
        emitter.emit(StreamEvent(type=StreamEventType.FIRST_TOKEN, timestamp=100.5))
        emitter.emit(StreamEvent(type=StreamEventType.STREAM_END, timestamp=102.0))
        
        metrics = emitter.get_metrics()
        assert metrics is not None
        assert metrics.request_start == 100.0
        assert metrics.first_token == 100.5
        assert metrics.stream_end == 102.0
    
    def test_callback_error_does_not_break_emission(self):
        """Callback errors should not break other callbacks."""
        emitter = StreamEventEmitter()
        events = []
        
        def bad_callback(event):
            raise ValueError("Test error")
        
        def good_callback(event):
            events.append(event)
        
        emitter.add_callback(bad_callback)
        emitter.add_callback(good_callback)
        
        event = StreamEvent(type=StreamEventType.DELTA_TEXT)
        emitter.emit(event)  # Should not raise
        
        assert len(events) == 1
    
    def test_reset_metrics(self):
        """Reset metrics should create new metrics."""
        emitter = StreamEventEmitter()
        emitter.enable_metrics()
        
        emitter.emit(StreamEvent(type=StreamEventType.REQUEST_START, timestamp=100.0))
        emitter.reset_metrics()
        
        metrics = emitter.get_metrics()
        assert metrics.request_start == 0.0


class TestHelperFunctions:
    """Tests for helper functions."""
    
    def test_create_text_printer_callback(self, capsys):
        """Text printer callback should print content."""
        callback = create_text_printer_callback(flush=True)
        
        callback(StreamEvent(type=StreamEventType.DELTA_TEXT, content="Hello"))
        callback(StreamEvent(type=StreamEventType.DELTA_TEXT, content=" World"))
        callback(StreamEvent(type=StreamEventType.STREAM_END))
        
        captured = capsys.readouterr()
        assert "Hello World" in captured.out
    
    def test_create_metrics_callback(self):
        """Metrics callback should update metrics."""
        metrics = StreamMetrics()
        callback = create_metrics_callback(metrics)
        
        callback(StreamEvent(type=StreamEventType.REQUEST_START, timestamp=100.0))
        callback(StreamEvent(type=StreamEventType.FIRST_TOKEN, timestamp=100.5))
        
        assert metrics.request_start == 100.0
        assert metrics.first_token == 100.5


class TestStreamingEventOrdering:
    """Tests for event ordering and pass-through behavior."""
    
    def test_events_emitted_immediately(self):
        """Events should be emitted immediately, not buffered."""
        emitter = StreamEventEmitter()
        timestamps = []
        
        def callback(event):
            timestamps.append((event.type, time.perf_counter()))
        
        emitter.add_callback(callback)
        
        # Simulate streaming with small delays
        emitter.emit(StreamEvent(type=StreamEventType.REQUEST_START))
        time.sleep(0.01)
        emitter.emit(StreamEvent(type=StreamEventType.FIRST_TOKEN))
        time.sleep(0.01)
        emitter.emit(StreamEvent(type=StreamEventType.DELTA_TEXT))
        
        # Verify events were captured in order
        assert len(timestamps) == 3
        assert timestamps[0][0] == StreamEventType.REQUEST_START
        assert timestamps[1][0] == StreamEventType.FIRST_TOKEN
        assert timestamps[2][0] == StreamEventType.DELTA_TEXT
        
        # Verify timestamps are increasing (no buffering)
        assert timestamps[0][1] < timestamps[1][1] < timestamps[2][1]
    
    def test_no_buffering_before_first_token(self):
        """Events should not be buffered before first token."""
        emitter = StreamEventEmitter()
        emitter.enable_metrics()
        
        # Emit request start
        t1 = time.perf_counter()
        emitter.emit(StreamEvent(type=StreamEventType.REQUEST_START, timestamp=t1))
        
        # Small delay (simulating network)
        time.sleep(0.05)
        
        # Emit first token
        t2 = time.perf_counter()
        emitter.emit(StreamEvent(type=StreamEventType.FIRST_TOKEN, timestamp=t2))
        
        metrics = emitter.get_metrics()
        
        # TTFT should reflect the actual delay
        assert metrics.ttft >= 0.04  # Allow some tolerance
