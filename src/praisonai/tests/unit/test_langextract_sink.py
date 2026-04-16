"""
Tests for LangextractSink adapter.

Unit tests for the langextract observability integration, focusing on:
- LangextractSink implements TraceSinkProtocol correctly
- Event-to-extraction mapping is accurate
- HTML output is generated correctly
- Lazy imports work properly
"""

import pytest
import tempfile
import time
import builtins
from pathlib import Path
from unittest.mock import Mock, patch

from praisonaiagents.trace.protocol import ActionEvent, ActionEventType


_REAL_IMPORT = builtins.__import__


def _import_with_langextract_failure(name, globals=None, locals=None, fromlist=(), level=0):
    """Import hook that fails only for langextract."""
    if name == "langextract":
        raise ImportError("No module named 'langextract'")
    return _REAL_IMPORT(name, globals, locals, fromlist, level)


@pytest.fixture
def sample_events():
    """Sample ActionEvents for testing."""
    ts = time.time()
    return [
        ActionEvent(
            event_type=ActionEventType.AGENT_START.value,
            timestamp=ts,
            agent_name="test_agent",
            metadata={"input": "Test input for the agent to process"}
        ),
        ActionEvent(
            event_type=ActionEventType.TOOL_START.value,
            timestamp=ts + 1,
            agent_name="test_agent",
            tool_name="search",
            tool_args={"query": "test query"}
        ),
        ActionEvent(
            event_type=ActionEventType.TOOL_END.value,
            timestamp=ts + 2,
            agent_name="test_agent",
            tool_name="search",
            duration_ms=100.0,
            status="ok",
            tool_result_summary="Found 5 results"
        ),
        ActionEvent(
            event_type=ActionEventType.OUTPUT.value,
            timestamp=ts + 3,
            agent_name="test_agent",
            metadata={"content": "Final agent output based on search results"}
        ),
        ActionEvent(
            event_type=ActionEventType.AGENT_END.value,
            timestamp=ts + 4,
            agent_name="test_agent",
            duration_ms=500.0,
            status="ok"
        )
    ]


class TestLangextractSink:
    """Test LangextractSink implementation."""

    def test_lazy_import_without_langextract(self):
        """Test that LangextractSink can be imported without langextract installed."""
        # This should work even if langextract is not available
        from praisonai.observability import LangextractSink, LangextractSinkConfig
        
        config = LangextractSinkConfig()
        sink = LangextractSink(config=config)
        
        # Basic properties should work
        assert sink._config.enabled is True
        assert sink._closed is False

    def test_sink_config_defaults(self):
        """Test LangextractSinkConfig default values."""
        from praisonai.observability import LangextractSinkConfig
        
        config = LangextractSinkConfig()
        assert config.output_path == "praisonai-trace.html"
        assert config.jsonl_path is None
        assert config.document_id == "praisonai-run"
        assert config.auto_open is False
        assert config.include_llm_content is True
        assert config.include_tool_args is True
        assert config.enabled is True

    def test_sink_implements_protocol(self):
        """Test that LangextractSink implements TraceSinkProtocol."""
        from praisonai.observability import LangextractSink
        from praisonaiagents.trace.protocol import TraceSinkProtocol
        
        sink = LangextractSink()
        assert isinstance(sink, TraceSinkProtocol)
        
        # Protocol methods should exist
        assert hasattr(sink, 'emit')
        assert hasattr(sink, 'flush')
        assert hasattr(sink, 'close')

    def test_event_accumulation(self, sample_events):
        """Test that events are accumulated correctly."""
        from praisonai.observability import LangextractSink
        
        sink = LangextractSink()
        
        # Emit all events
        for event in sample_events:
            sink.emit(event)
        
        # Events should be stored
        assert len(sink._events) == len(sample_events)
        assert sink._source_text == "Test input for the agent to process"

    def test_disabled_sink_ignores_events(self, sample_events):
        """Test that disabled sink ignores all events."""
        from praisonai.observability import LangextractSink, LangextractSinkConfig
        
        config = LangextractSinkConfig(enabled=False)
        sink = LangextractSink(config=config)
        
        # Emit events
        for event in sample_events:
            sink.emit(event)
        
        # No events should be stored
        assert len(sink._events) == 0
        assert sink._source_text is None

    def test_events_to_extractions_mapping(self, sample_events):
        """Test that ActionEvents are mapped to langextract extractions correctly."""
        from praisonai.observability import LangextractSink
        
        # Mock langextract module
        mock_lx = Mock()
        mock_extraction = Mock()
        mock_lx.data.Extraction = Mock(return_value=mock_extraction)
        
        sink = LangextractSink()
        for event in sample_events:
            sink.emit(event)
        
        # Test the mapping function
        extractions = list(sink._events_to_extractions(mock_lx, "Test input text"))
        
        # AGENT_END is intentionally skipped in current implementation
        assert len(extractions) == 4
        
        # Check that each event type creates an extraction
        assert mock_lx.data.Extraction.call_count == 4

    @patch('webbrowser.open')
    def test_render_with_mock_langextract(self, mock_browser, sample_events):
        """Test rendering with mocked langextract."""
        from praisonai.observability import LangextractSink, LangextractSinkConfig
        
        # Mock langextract module
        mock_lx = Mock()
        mock_doc = Mock()
        mock_html = Mock()
        mock_html.data = "<html>Test HTML content</html>"
        
        mock_lx.data.AnnotatedDocument = Mock(return_value=mock_doc)
        mock_lx.data.Extraction = Mock()
        mock_lx.io.save_annotated_documents = Mock()
        mock_lx.visualize = Mock(return_value=mock_html)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test.html"
            config = LangextractSinkConfig(
                output_path=str(output_path),
                auto_open=True
            )
            sink = LangextractSink(config=config)
            
            # Emit events
            for event in sample_events:
                sink.emit(event)
            
            # Mock import of optional langextract dependency
            with patch.dict("sys.modules", {"langextract": mock_lx}):
                sink.close()
            
            # Verify HTML file was written
            assert output_path.exists()
            content = output_path.read_text()
            assert "Test HTML content" in content
            
            # Verify browser was opened
            mock_browser.assert_called_once()

    def test_close_idempotent(self, sample_events):
        """Test that close() can be called multiple times safely."""
        from praisonai.observability import LangextractSink
        
        sink = LangextractSink()
        for event in sample_events:
            sink.emit(event)
        
        # Mock langextract to avoid import error
        mock_lx = Mock()
        with patch.dict("sys.modules", {"langextract": mock_lx}):
            mock_lx.data.AnnotatedDocument = Mock()
            mock_lx.data.Extraction = Mock()
            mock_lx.io.save_annotated_documents = Mock()
            mock_lx.visualize = Mock(return_value=Mock(data="<html></html>"))
            
            # First close should work
            sink.close()
            assert sink._closed is True
            
            # Second close should be no-op
            sink.close()
            assert sink._closed is True

    def test_flush_no_op(self):
        """Test that flush() is a no-op."""
        from praisonai.observability import LangextractSink
        
        sink = LangextractSink()
        # Should not raise any exception
        sink.flush()

    def test_import_error_handling(self, sample_events):
        """Test graceful handling of langextract import error."""
        from praisonai.observability import LangextractSink
        
        sink = LangextractSink()
        for event in sample_events:
            sink.emit(event)
        
        # Force ImportError for optional dependency
        with patch("builtins.__import__", side_effect=_import_with_langextract_failure):
            # Should not raise, just log warning
            sink.close()
            assert sink._closed is True


class TestLangextractCLI:
    """Test langextract CLI commands."""

    @pytest.mark.parametrize("command", ["view", "render"])
    def test_cli_commands_exist(self, command):
        """Test that CLI commands are registered."""
        from praisonai.cli.commands.langextract import app
        
        # Check that the command exists
        commands = {cmd.name for cmd in app.registered_commands}
        assert command in commands

    def test_view_command_missing_file(self):
        """Test view command with missing JSONL file."""
        from praisonai.cli.commands.langextract import view
        import typer
        
        with pytest.raises(typer.Exit):
            view(Path("/nonexistent/file.jsonl"))

    def test_render_command_missing_yaml(self):
        """Test render command with missing YAML file."""
        from praisonai.cli.commands.langextract import render
        import typer
        
        with pytest.raises(typer.Exit):
            render(Path("/nonexistent/workflow.yaml"))


class TestLangextractObservabilitySetup:
    """Test CLI observability setup."""

    def test_observe_langextract_calls_setup(self):
        """Test that --observe langextract calls the setup function."""
        import praisonai.cli.app as cli_app
        mock_ctx = Mock(invoked_subcommand="test")

        with patch.object(cli_app, "_setup_langextract_observability") as mock_setup:
            cli_app.main_callback(ctx=mock_ctx, observe="langextract")

        # Setup should have been called
        mock_setup.assert_called_once()

    def test_observe_invalid_provider_error(self):
        """Test that invalid observe provider raises error."""
        import typer
        import praisonai.cli.app as cli_app
        mock_ctx = Mock(invoked_subcommand="test")

        with patch('sys.argv', ['praisonai', '--observe', 'invalid-provider']):
            with pytest.raises(typer.BadParameter, match="Unsupported observe provider"):
                cli_app.main_callback(ctx=mock_ctx, observe="invalid-provider")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
