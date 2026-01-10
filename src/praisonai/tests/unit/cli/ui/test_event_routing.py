"""
Tests for UI event routing.

Verifies:
1. Events are properly routed from InteractiveCore to backends
2. All event types are handled correctly
3. Streaming events work properly
4. Multi-agent events include agent name
"""

from praisonai.cli.ui.events import UIEventType, UIEvent
from praisonai.cli.ui.plain import PlainBackend


class TestUIEventType:
    """Test UIEventType enum."""

    def test_message_events_exist(self):
        """Message lifecycle events should exist."""
        assert UIEventType.MESSAGE_START
        assert UIEventType.MESSAGE_CHUNK
        assert UIEventType.MESSAGE_END

    def test_tool_events_exist(self):
        """Tool lifecycle events should exist."""
        assert UIEventType.TOOL_START
        assert UIEventType.TOOL_PROGRESS
        assert UIEventType.TOOL_END

    def test_approval_events_exist(self):
        """Approval flow events should exist."""
        assert UIEventType.APPROVAL_REQUEST
        assert UIEventType.APPROVAL_RESPONSE

    def test_status_events_exist(self):
        """Status events should exist."""
        assert UIEventType.STATUS_UPDATE
        assert UIEventType.STATUS_CLEAR

    def test_error_events_exist(self):
        """Error events should exist."""
        assert UIEventType.ERROR
        assert UIEventType.WARNING


class TestUIEvent:
    """Test UIEvent dataclass."""

    def test_event_has_timestamp(self):
        """UIEvent should auto-generate timestamp."""
        event = UIEvent(event_type=UIEventType.MESSAGE_START)
        assert event.timestamp is not None
        assert event.timestamp > 0

    def test_event_with_data(self):
        """UIEvent should accept data payload."""
        event = UIEvent(
            event_type=UIEventType.MESSAGE_CHUNK,
            data={'content': 'Hello'}
        )
        assert event.data['content'] == 'Hello'

    def test_event_with_agent_name(self):
        """UIEvent should accept agent name for multi-agent."""
        event = UIEvent(
            event_type=UIEventType.MESSAGE_START,
            agent_name='Researcher'
        )
        assert event.agent_name == 'Researcher'


class TestPlainBackendEventRouting:
    """Test PlainBackend event handling."""

    def test_message_start_with_agent_name(self, capsys):
        """MESSAGE_START with agent name should print agent prefix."""
        backend = PlainBackend()
        backend.emit(UIEventType.MESSAGE_START, {'agent_name': 'Coder'})
        
        captured = capsys.readouterr()
        assert '[Coder]' in captured.out

    def test_message_chunk_appends_content(self, capsys):
        """MESSAGE_CHUNK should append content to output."""
        backend = PlainBackend()
        backend.emit(UIEventType.MESSAGE_CHUNK, {'content': 'Hello '})
        backend.emit(UIEventType.MESSAGE_CHUNK, {'content': 'World'})
        
        captured = capsys.readouterr()
        assert 'Hello World' in captured.out

    def test_message_end_adds_newline(self, capsys):
        """MESSAGE_END should add newline if needed."""
        backend = PlainBackend()
        backend.emit(UIEventType.MESSAGE_START, {})
        backend.emit(UIEventType.MESSAGE_CHUNK, {'content': 'Test'})
        backend.emit(UIEventType.MESSAGE_END, {})
        
        captured = capsys.readouterr()
        assert captured.out.endswith('\n')

    def test_tool_start_shows_tool_name(self, capsys):
        """TOOL_START should show tool name."""
        backend = PlainBackend()
        backend.emit(UIEventType.TOOL_START, {'tool_name': 'read_file'})
        
        captured = capsys.readouterr()
        assert 'read_file' in captured.out

    def test_tool_end_shows_result(self, capsys):
        """TOOL_END should show result."""
        backend = PlainBackend()
        backend.emit(UIEventType.TOOL_END, {'result': 'File contents here'})
        
        captured = capsys.readouterr()
        assert 'File contents here' in captured.out

    def test_error_writes_to_stderr(self, capsys):
        """ERROR should write to stderr."""
        backend = PlainBackend()
        backend.emit(UIEventType.ERROR, {'message': 'Something went wrong'})
        
        captured = capsys.readouterr()
        assert 'Something went wrong' in captured.err
        assert 'Error' in captured.err

    def test_warning_writes_to_stderr(self, capsys):
        """WARNING should write to stderr."""
        backend = PlainBackend()
        backend.emit(UIEventType.WARNING, {'message': 'Be careful'})
        
        captured = capsys.readouterr()
        assert 'Be careful' in captured.err
        assert 'Warning' in captured.err

    def test_approval_request_shows_prompt(self, capsys):
        """APPROVAL_REQUEST should show prompt."""
        backend = PlainBackend()
        backend.emit(UIEventType.APPROVAL_REQUEST, {'prompt': 'Allow file write?'})
        
        captured = capsys.readouterr()
        assert 'Allow file write?' in captured.out
        assert '[y/n]' in captured.out


class TestStreamingBehavior:
    """Test streaming message behavior."""

    def test_streaming_preserves_partial_content(self, capsys):
        """Streaming should preserve partial content between chunks."""
        backend = PlainBackend()
        
        backend.emit(UIEventType.MESSAGE_START, {})
        backend.emit(UIEventType.MESSAGE_CHUNK, {'content': 'Hello '})
        backend.emit(UIEventType.MESSAGE_CHUNK, {'content': 'World '})
        backend.emit(UIEventType.MESSAGE_CHUNK, {'content': '!'})
        backend.emit(UIEventType.MESSAGE_END, {})
        
        captured = capsys.readouterr()
        assert 'Hello World !' in captured.out

    def test_multiple_messages_separated(self, capsys):
        """Multiple messages should be properly separated."""
        backend = PlainBackend()
        
        # First message
        backend.emit(UIEventType.MESSAGE_START, {})
        backend.emit(UIEventType.MESSAGE_CHUNK, {'content': 'First'})
        backend.emit(UIEventType.MESSAGE_END, {})
        
        # Second message
        backend.emit(UIEventType.MESSAGE_START, {})
        backend.emit(UIEventType.MESSAGE_CHUNK, {'content': 'Second'})
        backend.emit(UIEventType.MESSAGE_END, {})
        
        captured = capsys.readouterr()
        assert 'First' in captured.out
        assert 'Second' in captured.out
