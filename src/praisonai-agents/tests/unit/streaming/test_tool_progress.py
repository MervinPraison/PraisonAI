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

    def test_blocked_reader_does_not_hang_past_timeout(self):
        """If a reader stays blocked in readline() after the DIRECT child exits
        (e.g. a background child inherited the pipe), the call must fall back to
        a _StreamDrainTimeout within the budget instead of hanging indefinitely.

        This is distinct from a real process timeout: the direct child is gone,
        so the caller must NOT try to kill it.
        """
        import threading
        import time as _time

        from praisonaiagents.tools.shell_tools import (
            ShellTools,
            _StreamDrainTimeout,
        )

        release = threading.Event()

        class _BlockingStream:
            def readline(self):
                # Block until released, simulating a pipe held open by a
                # background child after the direct child has exited.
                release.wait(timeout=30)
                return ""

            def close(self):
                release.set()

        class _FakeProc:
            args = "x"
            stdout = _BlockingStream()
            stderr = None
            returncode = 0

            def wait(self, timeout=None):
                return 0  # direct child exits immediately

        st = ShellTools()
        start = _time.monotonic()
        try:
            st._communicate_streaming(_FakeProc(), timeout=1)
            assert False, "expected _StreamDrainTimeout for a blocked reader"
        except _StreamDrainTimeout:
            pass
        finally:
            release.set()
        elapsed = _time.monotonic() - start
        # Should return roughly within the drain grace, well under 30s.
        assert elapsed < 10, f"call hung for {elapsed:.1f}s instead of timing out"

    def test_drain_timeout_does_not_kill_exited_process(self, monkeypatch):
        """execute_command must report a drain-timeout WITHOUT killing the
        already-exited direct child (its PID may have been recycled)."""
        from praisonaiagents.tools import shell_tools as _shell_tools
        from praisonaiagents.tools.shell_tools import ShellTools, _StreamDrainTimeout

        monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")

        killed = {"called": False}

        class _FakeProc:
            args = ["x"]
            pid = -1
            returncode = 0

            def kill(self):
                killed["called"] = True

        monkeypatch.setattr(
            _shell_tools.subprocess, "Popen", lambda *a, **k: _FakeProc()
        )

        def _raise_drain_timeout(self, process, timeout):
            raise _StreamDrainTimeout()

        monkeypatch.setattr(
            ShellTools, "_communicate_streaming", _raise_drain_timeout
        )

        st = ShellTools()
        result = st.execute_command("echo hi", timeout=1)

        assert result["success"] is False
        assert result["exit_code"] == -1
        assert "timed out" in result["stderr"]
        assert killed["called"] is False, "drain-timeout must NOT kill the exited child"

    def test_real_timeout_kills_running_process(self, monkeypatch):
        """A genuine TimeoutExpired (direct child still running) must reach the
        kill path so the subprocess is terminated."""
        from praisonaiagents.tools import shell_tools as _shell_tools
        from praisonaiagents.tools.shell_tools import ShellTools

        monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")
        # Force the psutil-free fallback path so process.kill() is exercised.
        monkeypatch.setitem(sys.modules, "psutil", None)

        killed = {"called": False}

        class _FakeProc:
            args = ["x"]
            pid = -1
            returncode = 0

            def kill(self):
                killed["called"] = True

        monkeypatch.setattr(
            _shell_tools.subprocess, "Popen", lambda *a, **k: _FakeProc()
        )

        def _raise_timeout(self, process, timeout):
            raise subprocess.TimeoutExpired(cmd="x", timeout=timeout)

        monkeypatch.setattr(ShellTools, "_communicate_streaming", _raise_timeout)

        st = ShellTools()
        result = st.execute_command("sleep 100", timeout=1)

        assert result["success"] is False
        assert result["exit_code"] == -1
        assert killed["called"] is True, "real timeout must kill the running child"

    def test_timeout_kills_running_process_even_with_read_error(self):
        """A reader-thread failure recorded before a REAL process timeout must
        NOT short-circuit cleanup: TimeoutExpired is re-raised so the caller
        kills the still-running child."""
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
        except subprocess.TimeoutExpired:
            pass  # process still running -> caller's kill path runs
        except UnicodeDecodeError:
            assert False, "read error short-circuited the timeout/kill cleanup"
