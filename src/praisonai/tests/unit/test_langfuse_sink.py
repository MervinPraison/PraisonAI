"""
Unit tests for LangfuseSink observability adapter.

Tests verify:
1. LangfuseSinkConfig picks up env vars correctly
2. LangfuseSink raises ValueError (not ImportError) for missing credentials
3. LangfuseSink silently handles events when disabled
4. LangfuseSink correctly routes events to Langfuse API (via mocks)
5. flush() / close() lifecycle is handled correctly
6. Sink does not let errors propagate to calling code
7. Protocol compliance with TraceSinkProtocol
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from praisonaiagents.trace.context_events import ContextEvent, ContextEventType
from praisonaiagents.trace.protocol import ActionEvent, ActionEventType, TraceSinkProtocol
from praisonai.observability.langfuse import LangfuseSink, LangfuseSinkConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(event_type, agent_name="agent1", **kwargs):
    """Create an ActionEvent for testing."""
    return ActionEvent(
        event_type=event_type,
        timestamp=time.time(),
        agent_name=agent_name,
        **kwargs,
    )


def _make_sink_with_mock_client():
    """Return a sink with a mock Langfuse client already injected."""
    cfg = LangfuseSinkConfig(enabled=False)
    sink = LangfuseSink(cfg)
    sink._client = MagicMock()
    sink._config.enabled = True
    return sink


# ---------------------------------------------------------------------------
# LangfuseSinkConfig tests
# ---------------------------------------------------------------------------

class TestLangfuseSinkConfig:
    def test_defaults_when_env_empty(self, monkeypatch):
        """Config falls back to the default cloud host when env vars not set."""
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)

        cfg = LangfuseSinkConfig(enabled=False)
        assert cfg.public_key == ""
        assert cfg.secret_key == ""
        assert cfg.host == "https://cloud.langfuse.com"

    def test_reads_env_vars(self, monkeypatch):
        """Config reads credentials from env vars."""
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3000")

        cfg = LangfuseSinkConfig()
        assert cfg.public_key == "pk-test"
        assert cfg.secret_key == "sk-test"
        assert cfg.host == "http://localhost:3000"

    def test_explicit_values_take_precedence(self, monkeypatch):
        """Explicitly provided values override env vars."""
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-env")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-env")

        cfg = LangfuseSinkConfig(public_key="pk-explicit", secret_key="sk-explicit")
        assert cfg.public_key == "pk-explicit"
        assert cfg.secret_key == "sk-explicit"

    def test_enabled_false_with_no_credentials(self, monkeypatch):
        """Disabled config doesn't need credentials."""
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

        cfg = LangfuseSinkConfig(enabled=False)
        assert cfg.enabled is False


# ---------------------------------------------------------------------------
# LangfuseSink initialization tests
# ---------------------------------------------------------------------------

class TestLangfuseSinkInit:
    def test_disabled_sink_does_not_initialize_client(self):
        """Disabled sink should not attempt to import langfuse."""
        cfg = LangfuseSinkConfig(enabled=False)
        sink = LangfuseSink(cfg)
        assert sink._client is None
        assert sink._closed is False

    def test_missing_credentials_raises_value_error(self, monkeypatch):
        """ValueError (not ImportError) raised when credentials missing."""
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

        cfg = LangfuseSinkConfig(public_key="", secret_key="", enabled=True)
        with patch.dict("sys.modules", {"langfuse": MagicMock()}):
            with pytest.raises(ValueError, match="credentials missing"):
                LangfuseSink(cfg)

    def test_initialized_with_valid_credentials(self, monkeypatch):
        """Sink initializes successfully with valid credentials."""
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

        mock_langfuse_module = MagicMock()
        mock_client = MagicMock()
        mock_langfuse_module.Langfuse.return_value = mock_client

        cfg = LangfuseSinkConfig()
        with patch.dict("sys.modules", {"langfuse": mock_langfuse_module}):
            sink = LangfuseSink(cfg)

        assert sink._client is mock_client


# ---------------------------------------------------------------------------
# LangfuseSink event emission tests
# ---------------------------------------------------------------------------

class TestLangfuseSinkEmit:
    def test_emit_agent_start_creates_trace_and_span(self):
        """AGENT_START event creates a trace and root span."""
        sink = _make_sink_with_mock_client()
        mock_span = MagicMock()
        sink._client.start_observation.return_value = mock_span

        event = _make_event(ActionEventType.AGENT_START.value)
        sink.emit(event)

        sink._client.start_observation.assert_called_once()
        call_kwargs = sink._client.start_observation.call_args.kwargs
        assert call_kwargs.get("as_type") == "span"
        assert "agent1-agent1" in sink._traces
        assert "agent1-agent1" in sink._spans

    def test_emit_agent_end_ends_span(self):
        """AGENT_END event ends the root span."""
        sink = _make_sink_with_mock_client()
        mock_span = MagicMock()
        sink._spans["agent1-agent1"] = mock_span
        sink._traces["agent1-agent1"] = MagicMock()

        event = _make_event(ActionEventType.AGENT_END.value, status="ok")
        sink.emit(event)

        mock_span.end.assert_called_once()
        assert "agent1-agent1" not in sink._spans
        assert "agent1-agent1" not in sink._traces

    def test_emit_tool_start_creates_child_span(self):
        """TOOL_START creates a child span under the parent agent span."""
        sink = _make_sink_with_mock_client()
        mock_parent_span = MagicMock()
        mock_tool_span = MagicMock()
        sink._client.start_observation.return_value = mock_tool_span
        sink._spans["agent1-agent1"] = mock_parent_span

        event = _make_event(
            ActionEventType.TOOL_START.value,
            tool_name="search_tool",
            tool_args={"query": "test"},
        )
        sink.emit(event)

        sink._client.start_observation.assert_called_once()
        call_kwargs = sink._client.start_observation.call_args.kwargs
        assert call_kwargs.get("name") == "search_tool"
        
        tool_keys = [k for k in sink._spans if k.startswith("agent1-agent1:search_tool:")]
        assert len(tool_keys) == 1

    def test_emit_tool_end_closes_tool_span(self):
        """TOOL_END ends the matching tool span."""
        sink = _make_sink_with_mock_client()
        mock_tool_span = MagicMock()
        ts = str(time.time())
        sink._spans[f"agent1-agent1:search_tool:{ts}"] = mock_tool_span

        event = _make_event(
            ActionEventType.TOOL_END.value,
            tool_name="search_tool",
            duration_ms=100.0,
            status="ok",
            tool_result_summary="result",
        )
        sink.emit(event)

        mock_tool_span.end.assert_called_once()

    def test_emit_error_creates_error_event(self):
        """ERROR event creates a Langfuse event with level=ERROR."""
        sink = _make_sink_with_mock_client()

        event = _make_event(
            ActionEventType.ERROR.value,
            error_message="Something went wrong",
        )
        sink.emit(event)

        sink._client.start_observation.assert_called_once()
        call_kwargs = sink._client.start_observation.call_args.kwargs
        assert call_kwargs.get("as_type") == "event"
        assert call_kwargs.get("level") == "ERROR"

    def test_emit_output_creates_output_event(self):
        """OUTPUT event creates a Langfuse event."""
        sink = _make_sink_with_mock_client()

        event = _make_event(
            ActionEventType.OUTPUT.value,
            tool_result_summary="Final answer",
        )
        sink.emit(event)

        sink._client.start_observation.assert_called_once()
        call_kwargs = sink._client.start_observation.call_args.kwargs
        assert call_kwargs.get("as_type") == "event"
        assert call_kwargs.get("name") == "output"

    def test_emit_when_disabled_is_noop(self):
        """emit() does nothing when sink is disabled."""
        cfg = LangfuseSinkConfig(enabled=False)
        sink = LangfuseSink(cfg)
        mock_client = MagicMock()
        sink._client = mock_client

        event = _make_event(ActionEventType.AGENT_START.value)
        sink.emit(event)

        mock_client.trace.assert_not_called()

    def test_emit_when_closed_is_noop(self):
        """emit() does nothing after close()."""
        sink = _make_sink_with_mock_client()
        sink._closed = True

        event = _make_event(ActionEventType.AGENT_START.value)
        sink.emit(event)

        sink._client.trace.assert_not_called()

    def test_emit_exception_does_not_propagate(self):
        """Exceptions inside emit() are caught and do not bubble up."""
        sink = _make_sink_with_mock_client()
        sink._client.trace.side_effect = RuntimeError("Langfuse network error")

        event = _make_event(ActionEventType.AGENT_START.value)
        sink.emit(event)  # Must NOT raise


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------

class TestLangfuseSinkLifecycle:
    def test_flush_calls_client_flush(self):
        sink = _make_sink_with_mock_client()
        sink.flush()
        sink._client.flush.assert_called_once()

    def test_flush_after_close_is_noop(self):
        sink = _make_sink_with_mock_client()
        sink.close()
        sink._client.flush.reset_mock()
        sink.flush()
        sink._client.flush.assert_not_called()

    def test_close_flushes_and_closes_remaining_spans(self):
        sink = _make_sink_with_mock_client()
        mock_span = MagicMock()
        sink._spans["agent1-agent1"] = mock_span

        sink.close()

        sink._client.flush.assert_called_once()
        mock_span.end.assert_called_once()
        assert sink._closed is True
        assert not sink._spans

    def test_double_close_is_safe(self):
        sink = _make_sink_with_mock_client()
        sink.close()
        sink.close()  # Should not raise


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

class TestLangfuseSinkProtocol:
    def test_implements_trace_sink_protocol(self):
        """LangfuseSink satisfies TraceSinkProtocol at runtime."""
        sink = LangfuseSink(LangfuseSinkConfig(enabled=False))
        assert isinstance(sink, TraceSinkProtocol)


class TestLangfuseContextBridge:
    def test_context_tool_end_maps_result_and_status(self):
        sink = _make_sink_with_mock_client()
        bridge = sink.context_sink()

        event = ContextEvent(
            event_type=ContextEventType.TOOL_CALL_END,
            timestamp=time.time(),
            session_id="session-1",
            agent_name="agent1",
            data={
                "tool_name": "search_tool",
                "result": "ok",
                "duration_ms": 12.0,
            },
        )

        action_event = bridge._convert_context_to_action(event)
        assert action_event is not None
        assert action_event.tool_result_summary == "ok"
        assert action_event.status == "completed"
        assert action_event.error_message is None

    def test_context_tool_end_maps_error(self):
        sink = _make_sink_with_mock_client()
        bridge = sink.context_sink()

        event = ContextEvent(
            event_type=ContextEventType.TOOL_CALL_END,
            timestamp=time.time(),
            session_id="session-1",
            agent_name="agent1",
            data={
                "tool_name": "search_tool",
                "error": "failed",
            },
        )

        action_event = bridge._convert_context_to_action(event)
        assert action_event is not None
        assert action_event.status == "error"
        assert action_event.error_message == "failed"
