"""Tests for MCP stdio fail-closed behaviour (issue #4375).

A stdio MCP server that times out, errors on init, or lists zero tools must
raise instead of returning a usable-but-empty MCP object. Otherwise
``Agent(tools=mcp)`` silently degrades into a tool-less chat and the model
hallucinates answers with ``n_tools == 0``.
"""

import threading
from unittest.mock import patch

import pytest

from praisonaiagents.mcp import mcp as mcp_module
from praisonaiagents.mcp.mcp import MCP


class _FakeRunner:
    """Stand-in for MCPToolRunner that skips the real stdio subprocess."""

    def __init__(self, server_params, timeout=60, *, tools=None,
                 init_ok=True, init_error=None):
        self.server_params = server_params
        self.timeout = timeout
        self.tools = tools if tools is not None else []
        self.resources = []
        self.resource_templates = []
        self.prompts = []
        self._init_error = init_error
        self.initialized = threading.Event()
        if init_ok:
            self.initialized.set()

    def shutdown(self):
        pass

    def stop(self):
        pass


def _make_runner_factory(**runner_kwargs):
    def factory(server_params, timeout=60):
        return _FakeRunner(server_params, timeout, **runner_kwargs)
    return factory


@pytest.mark.skipif(not mcp_module.MCP_AVAILABLE, reason="mcp package not installed")
def test_mcp_empty_tools_raises():
    """A server that lists zero tools raises RuntimeError, not [] ."""
    with patch.object(mcp_module, "MCPToolRunner", _make_runner_factory(tools=[])):
        with pytest.raises(RuntimeError, match="produced 0 tools"):
            MCP("/usr/bin/python fake_server.py", timeout=5)


@pytest.mark.skipif(not mcp_module.MCP_AVAILABLE, reason="mcp package not installed")
def test_mcp_timeout_raises():
    """An init timeout raises TimeoutError instead of printing a warning."""
    factory = _make_runner_factory(init_ok=False)
    with patch.object(mcp_module, "MCPToolRunner", factory):
        with pytest.raises(TimeoutError, match="timed out"):
            MCP("/usr/bin/python fake_server.py", timeout=1)


@pytest.mark.skipif(not mcp_module.MCP_AVAILABLE, reason="mcp package not installed")
def test_mcp_init_error_raises():
    """An init error surfaced by the runner raises RuntimeError."""
    factory = _make_runner_factory(init_error="boom while starting server")
    with patch.object(mcp_module, "MCPToolRunner", factory):
        with pytest.raises(RuntimeError, match="initialization failed"):
            MCP("/usr/bin/python fake_server.py", timeout=5)


@pytest.mark.skipif(not mcp_module.MCP_AVAILABLE, reason="mcp package not installed")
def test_mcp_nonempty_tools_ok():
    """A server that lists at least one tool constructs successfully."""
    class _FakeTool:
        name = "get_current_time"
        description = "Return the current time"
        inputSchema = {"type": "object", "properties": {}, "required": []}

    factory = _make_runner_factory(tools=[_FakeTool()])
    with patch.object(mcp_module, "MCPToolRunner", factory):
        mcp = MCP("/usr/bin/python fake_server.py", timeout=5)
        names = [getattr(t, "__name__", None) for t in mcp]
        assert "get_current_time" in names
        assert len(list(mcp)) == len(mcp.get_tools())


@pytest.mark.skipif(not mcp_module.MCP_AVAILABLE, reason="mcp package not installed")
def test_mcp_empty_server_with_filter_still_raises():
    """A filter must not mask a server that advertised zero tools.

    When the server itself lists no tools, the filter removed nothing, so the
    fail-closed error must still fire even though allowed_tools was supplied
    (issue #4375).
    """
    factory = _make_runner_factory(tools=[])
    with patch.object(mcp_module, "MCPToolRunner", factory):
        with pytest.raises(RuntimeError, match="produced 0 tools"):
            MCP("/usr/bin/python fake_server.py", timeout=5,
                allowed_tools=["get_current_time"])


@pytest.mark.skipif(not mcp_module.MCP_AVAILABLE, reason="mcp package not installed")
def test_mcp_filter_removes_all_tools_does_not_raise():
    """A filter that deliberately removes every tool is a valid empty config."""
    class _FakeTool:
        name = "get_current_time"
        description = "Return the current time"
        inputSchema = {"type": "object", "properties": {}, "required": []}

    factory = _make_runner_factory(tools=[_FakeTool()])
    with patch.object(mcp_module, "MCPToolRunner", factory):
        mcp = MCP("/usr/bin/python fake_server.py", timeout=5,
                  disabled_tools=["get_current_time"])
        assert list(mcp) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
