"""Regression tests for MCP.shutdown() joining the runner thread (issue #5074)."""

import threading
import time

from unittest.mock import MagicMock


def _dead_runner():
    """A runner mock that reports its thread has already exited."""
    runner = MagicMock()
    runner.is_alive.return_value = False
    return runner


def test_mcp_shutdown_invokes_stop():
    """MCP.shutdown() must call both shutdown() and stop() on the runner so the
    daemon thread is joined and its stdio subprocess terminated, not just
    signalled with a sentinel."""
    from praisonaiagents.mcp.mcp import MCP

    runner = _dead_runner()
    mcp = MCP.__new__(MCP)
    mcp.runner = runner

    mcp.shutdown()

    runner.shutdown.assert_called_once()
    runner.stop.assert_called_once()
    assert mcp.runner is None


def test_mcp_shutdown_is_idempotent():
    """A second shutdown() after runner is cleared must not raise."""
    from praisonaiagents.mcp.mcp import MCP

    runner = _dead_runner()
    mcp = MCP.__new__(MCP)
    mcp.runner = runner

    mcp.shutdown()
    mcp.shutdown()

    runner.stop.assert_called_once()


def test_mcp_shutdown_tolerates_runner_errors():
    """Errors from shutdown()/stop() are swallowed (best-effort cleanup)."""
    from praisonaiagents.mcp.mcp import MCP

    runner = _dead_runner()
    runner.shutdown.side_effect = RuntimeError("boom")
    runner.stop.side_effect = RuntimeError("boom")
    mcp = MCP.__new__(MCP)
    mcp.runner = runner

    mcp.shutdown()

    assert mcp.runner is None


def test_mcp_shutdown_keeps_runner_if_thread_still_alive():
    """If the runner thread outlives the join timeout, shutdown() must keep the
    reference so a later shutdown() can retry the join (issue #5074)."""
    from praisonaiagents.mcp.mcp import MCP

    runner = MagicMock()
    runner.is_alive.return_value = True
    mcp = MCP.__new__(MCP)
    mcp.runner = runner

    mcp.shutdown()

    runner.stop.assert_called_once()
    assert mcp.runner is runner

    # A later shutdown() after the thread has exited clears the reference.
    runner.is_alive.return_value = False
    mcp.shutdown()
    assert mcp.runner is None


def test_runner_stop_joins_live_thread():
    """MCPToolRunner.stop() enqueues the sentinel and actually joins a live
    worker thread that exits when it observes the sentinel."""
    from unittest.mock import patch
    from praisonaiagents.mcp.mcp import MCPToolRunner

    with patch.object(MCPToolRunner, "start", lambda self: None):
        runner = MCPToolRunner(server_params=MagicMock(), timeout=5)

    # Simulate the real request loop: block on the queue until the sentinel
    # (None) arrives, then exit — mirroring _run_async()'s shutdown path.
    def _worker():
        while True:
            if runner.queue.get() is None:
                break

    thread = threading.Thread(target=_worker, daemon=True)
    # Rebind the Thread-provided join/is_alive to the worker so stop() operates
    # on a genuinely running thread.
    runner.is_alive = thread.is_alive
    runner.join = thread.join
    thread.start()

    assert thread.is_alive()
    runner.stop(timeout=5)

    # Give the worker a beat to unwind after join returns.
    time.sleep(0.05)
    assert not thread.is_alive()


def test_runner_stop_defaults_join_timeout_to_operation_timeout():
    """stop() with no explicit timeout joins using the runner's own timeout."""
    from unittest.mock import patch
    from praisonaiagents.mcp.mcp import MCPToolRunner

    with patch.object(MCPToolRunner, "start", lambda self: None):
        runner = MCPToolRunner(server_params=MagicMock(), timeout=7)

    runner.is_alive = MagicMock(return_value=True)
    runner.join = MagicMock()

    runner.stop()

    assert runner.queue.get_nowait() is None
    runner.join.assert_called_once_with(timeout=7)
