"""Regression tests for MCP.shutdown() joining the runner thread (issue #5074)."""

from unittest.mock import MagicMock


def test_mcp_shutdown_invokes_stop():
    """MCP.shutdown() must call both shutdown() and stop() on the runner so the
    daemon thread is joined and its stdio subprocess terminated, not just
    signalled with a sentinel."""
    from praisonaiagents.mcp.mcp import MCP

    runner = MagicMock()
    mcp = MCP.__new__(MCP)
    mcp.runner = runner

    mcp.shutdown()

    runner.shutdown.assert_called_once()
    runner.stop.assert_called_once()
    assert mcp.runner is None


def test_mcp_shutdown_is_idempotent():
    """A second shutdown() after runner is cleared must not raise."""
    from praisonaiagents.mcp.mcp import MCP

    runner = MagicMock()
    mcp = MCP.__new__(MCP)
    mcp.runner = runner

    mcp.shutdown()
    mcp.shutdown()

    runner.stop.assert_called_once()


def test_mcp_shutdown_tolerates_runner_errors():
    """Errors from shutdown()/stop() are swallowed (best-effort cleanup)."""
    from praisonaiagents.mcp.mcp import MCP

    runner = MagicMock()
    runner.shutdown.side_effect = RuntimeError("boom")
    runner.stop.side_effect = RuntimeError("boom")
    mcp = MCP.__new__(MCP)
    mcp.runner = runner

    mcp.shutdown()

    assert mcp.runner is None


def test_runner_stop_joins_thread():
    """MCPToolRunner.stop() enqueues the sentinel and joins the live thread."""
    from unittest.mock import patch
    from praisonaiagents.mcp.mcp import MCPToolRunner

    with patch.object(MCPToolRunner, "start", lambda self: None):
        runner = MCPToolRunner(server_params=MagicMock(), timeout=5)

    runner.stop()

    assert runner.queue.get_nowait() is None
