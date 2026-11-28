"""
Unit tests for MCPHandler.create_mcp_from_server.

Verifies that the run path can build MCP instances from structured server
config dicts for both local (stdio) and remote (URL) transports, so multiple
and remote MCP servers declared in project config are all wired — not just the
first stdio server.
"""

from contextlib import contextmanager
from unittest.mock import patch

from praisonai.cli.features.mcp import MCPHandler
from praisonaiagents.mcp.mcp import MCP


class _Calls:
    """What MCP.__init__ was called with; no server is started."""

    def __init__(self):
        self.call_args = None

    def assert_not_called(self):
        assert self.call_args is None, self.call_args


@contextmanager
def _record_mcp():
    calls = _Calls()

    def fake_init(self, target=None, args=None, **kw):
        calls.call_args = ((target,), {"command": target, "args": args, **kw})

    with patch.object(MCP, "__init__", fake_init):
        yield calls


class TestCreateMCPFromServer:
    """create_mcp_from_server handles local + remote server dicts."""

    def _patched_handler(self):
        handler = MCPHandler(verbose=False)
        # Dependencies are always considered available for the unit test.
        handler.check_dependencies = lambda: (True, "")
        return handler

    def test_local_server_list_command(self):
        handler = self._patched_handler()
        with _record_mcp() as mock_mcp:
            result = handler.create_mcp_from_server(
                {"command": ["npx", "-y", "@playwright/mcp"], "args": ["--headless"]}
            )
        assert result is not None
        _, kwargs = mock_mcp.call_args
        assert kwargs["command"] == "npx"
        assert kwargs["args"] == ["-y", "@playwright/mcp", "--headless"]

    def test_local_server_string_command_with_env(self):
        handler = self._patched_handler()
        with _record_mcp() as mock_mcp:
            handler.create_mcp_from_server(
                {"command": "npx -y @pg/mcp", "env": {"PG_URL": "postgres://x"}}
            )
        _, kwargs = mock_mcp.call_args
        assert kwargs["command"] == "npx"
        assert kwargs["args"] == ["-y", "@pg/mcp"]
        assert kwargs["env"] == {"PG_URL": "postgres://x"}

    def test_remote_server_with_headers(self):
        handler = self._patched_handler()
        with _record_mcp() as mock_mcp:
            result = handler.create_mcp_from_server(
                {
                    "type": "remote",
                    "url": "http://localhost:8080/mcp",
                    "headers": {"Authorization": "Bearer xyz"},
                }
            )
        assert result is not None
        args, kwargs = mock_mcp.call_args
        assert args[0] == "http://localhost:8080/mcp"
        assert kwargs["headers"] == {"Authorization": "Bearer xyz"}

    def test_remote_inferred_from_url(self):
        handler = self._patched_handler()
        with _record_mcp() as mock_mcp:
            handler.create_mcp_from_server({"url": "http://remote/mcp"})
        args, _ = mock_mcp.call_args
        assert args[0] == "http://remote/mcp"

    def test_disabled_server_skipped(self):
        handler = self._patched_handler()
        with _record_mcp() as mock_mcp:
            result = handler.create_mcp_from_server(
                {"command": ["npx", "x"], "enabled": False}
            )
        assert result is None
        mock_mcp.assert_not_called()

    def test_disallowed_command_rejected(self):
        handler = self._patched_handler()
        with _record_mcp() as mock_mcp:
            result = handler.create_mcp_from_server({"command": ["rm", "-rf", "/"]})
        assert result is None
        mock_mcp.assert_not_called()

    def test_inline_code_execution_rejected(self):
        """An allowed interpreter with an inline-eval flag must be rejected,
        matching the ad-hoc ``--mcp`` string path (no config bypass)."""
        handler = self._patched_handler()
        for server in (
            {"command": ["python", "-c", "print(1)"]},
            {"command": "python -c 'print(1)'"},
            {"command": ["node", "-e", "1"]},
            {"command": ["deno", "eval", "1"]},
        ):
            with _record_mcp() as mock_mcp:
                result = handler.create_mcp_from_server(server)
            assert result is None
            mock_mcp.assert_not_called()

    def test_sse_url_authorization_header_refused(self):
        """Legacy SSE URLs cannot forward headers (SDK limitation): an
        Authorization header is refused rather than connecting without it."""
        handler = self._patched_handler()
        with _record_mcp() as mock_mcp:
            result = handler.create_mcp_from_server(
                {"url": "http://localhost:8080/sse", "headers": {"Authorization": "Bearer xyz"}}
            )
        assert result is None
        mock_mcp.assert_not_called()

    def test_sse_url_other_headers_dropped(self):
        handler = self._patched_handler()
        with _record_mcp() as mock_mcp:
            result = handler.create_mcp_from_server(
                {"url": "http://localhost:8080/sse", "headers": {"X-A": "1"}}
            )
        assert result is not None
        _, kwargs = mock_mcp.call_args
        assert "headers" not in kwargs

    def test_small_millisecond_timeout_stays_milliseconds(self):
        handler = self._patched_handler()
        with _record_mcp() as mock_mcp:
            handler.create_mcp_from_server({"command": ["npx", "x"], "timeout": 500})
        _, kwargs = mock_mcp.call_args
        assert kwargs["timeout"] == 1

    def test_timeout_milliseconds_converted_to_seconds(self):
        handler = self._patched_handler()
        with _record_mcp() as mock_mcp:
            handler.create_mcp_from_server(
                {"command": ["npx", "x"], "timeout": 30000}
            )
        _, kwargs = mock_mcp.call_args
        assert kwargs["timeout"] == 30
