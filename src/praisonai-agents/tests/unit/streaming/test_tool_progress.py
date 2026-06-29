"""
Unit tests for the tool-progress streaming channel.

Covers:
- TOOL_PROGRESS event type exists
- emit_tool_progress is a no-op (returns False) when no sink is active
- tool_progress_channel activates a sink that receives TOOL_PROGRESS events
- The sink is cleared after the context manager exits
- ShellTools._communicate_streaming emits incremental progress and still
  returns the full buffered (stdout, stderr) output
"""

import subprocess
import sys

from praisonaiagents.streaming.events import (
    StreamEvent,
    StreamEventType,
    emit_tool_progress,
    tool_progress_channel,
)


class TestToolProgressChannel:
    def test_tool_progress_event_type_exists(self):
        assert StreamEventType.TOOL_PROGRESS.value == "tool_progress"

    def test_emit_is_noop_without_sink(self):
        assert emit_tool_progress("nothing listening") is False

    def test_emit_forwards_to_active_sink(self):
        events = []
        with tool_progress_channel(events.append):
            assert emit_tool_progress("line1", progress=0.5,
                                      metadata={"stream": "stdout"}) is True
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, StreamEvent)
        assert evt.type == StreamEventType.TOOL_PROGRESS
        assert evt.content == "line1"
        assert evt.metadata["stream"] == "stdout"
        assert evt.metadata["progress"] == 0.5

    def test_sink_cleared_after_context(self):
        with tool_progress_channel(lambda e: None):
            assert emit_tool_progress("x") is True
        assert emit_tool_progress("y") is False

    def test_none_sink_is_zero_overhead(self):
        with tool_progress_channel(None):
            assert emit_tool_progress("x") is False

    def test_none_sink_clears_inherited_sink(self):
        outer = []
        with tool_progress_channel(outer.append):
            assert emit_tool_progress("outer") is True
            # A nested no-callback channel must NOT leak into the parent sink.
            with tool_progress_channel(None):
                assert emit_tool_progress("inner") is False
            # Parent sink is restored after the nested context exits.
            assert emit_tool_progress("outer-again") is True
        assert [e.content for e in outer] == ["outer", "outer-again"]


class TestShellStreaming:
    def test_communicate_streaming_emits_and_buffers(self):
        from praisonaiagents.tools.shell_tools import ShellTools

        st = ShellTools()
        proc = subprocess.Popen(
            [sys.executable, "-c", "print('a'); print('b'); print('c')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        events = []
        with tool_progress_channel(events.append):
            out, err = st._communicate_streaming(proc, timeout=10)

        assert out == "a\nb\nc\n"
        assert err == ""
        contents = [e.content.strip() for e in events]
        assert contents == ["a", "b", "c"]
        assert all(e.type == StreamEventType.TOOL_PROGRESS for e in events)
        assert all(e.metadata["stream"] == "stdout" for e in events)

    def test_communicate_streaming_emits_stderr(self):
        from praisonaiagents.tools.shell_tools import ShellTools

        st = ShellTools()
        proc = subprocess.Popen(
            [sys.executable, "-c", "import sys; print('err', file=sys.stderr)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        events = []
        with tool_progress_channel(events.append):
            out, err = st._communicate_streaming(proc, timeout=10)

        assert out == ""
        assert err == "err\n"
        assert [e.content.strip() for e in events] == ["err"]
        assert all(e.metadata["stream"] == "stderr" for e in events)

    def test_communicate_streaming_without_sink(self):
        from praisonaiagents.tools.shell_tools import ShellTools

        st = ShellTools()
        proc = subprocess.Popen(
            [sys.executable, "-c", "print('hello')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        out, err = st._communicate_streaming(proc, timeout=10)
        assert out == "hello\n"
        assert err == ""

    def test_timeout_surfaces_recorded_read_error(self):
        """A reader-thread failure recorded before a timeout must not be masked
        by the generic TimeoutExpired — the real read error is surfaced."""
        from praisonaiagents.tools.shell_tools import ShellTools

        class _FailingStream:
            def readline(self):
                raise UnicodeDecodeError("utf-8", b"", 0, 1, "boom")

            def close(self):
                pass

        class _FakeProc:
            stdout = _FailingStream()
            stderr = None

            def wait(self, timeout=None):
                import time
                time.sleep(0.05)
                raise subprocess.TimeoutExpired(cmd="x", timeout=timeout)

        st = ShellTools()
        try:
            st._communicate_streaming(_FakeProc(), timeout=0.01)
            assert False, "expected an exception"
        except UnicodeDecodeError:
            pass  # read error surfaced instead of TimeoutExpired
        except subprocess.TimeoutExpired:
            assert False, "timeout masked the recorded read error"
