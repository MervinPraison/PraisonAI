"""
Unit tests for MCPHandler.create_mcp_from_server.

Verifies that the run path can build MCP instances from structured server
config dicts for both local (stdio) and remote (URL) transports, so multiple
and remote MCP servers declared in project config are all wired — not just the
first stdio server.
"""

from unittest.mock import patch

from praisonai.cli.features.mcp import MCPHandler


class TestCreateMCPFromServer:
    """create_mcp_from_server handles local + remote server dicts."""

    def _patched_handler(self):
        handler = MCPHandler(verbose=False)
        # Dependencies are always considered available for the unit test.
        handler.check_dependencies = lambda: (True, "")
        return handler

    def test_local_server_list_command(self):
        handler = self._patched_handler()
        with patch("praisonaiagents.MCP") as mock_mcp:
            mock_mcp.return_value = object()
            result = handler.create_mcp_from_server(
                {"command": ["npx", "-y", "@playwright/mcp"], "args": ["--headless"]}
            )
        assert result is not None
        _, kwargs = mock_mcp.call_args
        assert kwargs["command"] == "npx"
        assert kwargs["args"] == ["-y", "@playwright/mcp", "--headless"]

    def test_local_server_string_command_with_env(self):
        handler = self._patched_handler()
        with patch("praisonaiagents.MCP") as mock_mcp:
            mock_mcp.return_value = object()
            handler.create_mcp_from_server(
                {"command": "npx -y @pg/mcp", "env": {"PG_URL": "postgres://x"}}
            )
        _, kwargs = mock_mcp.call_args
        assert kwargs["command"] == "npx"
        assert kwargs["args"] == ["-y", "@pg/mcp"]
        assert kwargs["env"] == {"PG_URL": "postgres://x"}

    def test_remote_server_with_headers(self):
        handler = self._patched_handler()
        with patch("praisonaiagents.MCP") as mock_mcp:
            mock_mcp.return_value = object()
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
        with patch("praisonaiagents.MCP") as mock_mcp:
            mock_mcp.return_value = object()
            handler.create_mcp_from_server({"url": "http://remote/mcp"})
        args, _ = mock_mcp.call_args
        assert args[0] == "http://remote/mcp"

    def test_disabled_server_skipped(self):
        handler = self._patched_handler()
        with patch("praisonaiagents.MCP") as mock_mcp:
            result = handler.create_mcp_from_server(
                {"command": ["npx", "x"], "enabled": False}
            )
        assert result is None
        mock_mcp.assert_not_called()

    def test_disallowed_command_rejected(self):
        handler = self._patched_handler()
        with patch("praisonaiagents.MCP") as mock_mcp:
            result = handler.create_mcp_from_server({"command": ["rm", "-rf", "/"]})
        assert result is None
        mock_mcp.assert_not_called()

    def test_timeout_milliseconds_converted_to_seconds(self):
        handler = self._patched_handler()
        with patch("praisonaiagents.MCP") as mock_mcp:
            mock_mcp.return_value = object()
            handler.create_mcp_from_server(
                {"command": ["npx", "x"], "timeout": 30000}
            )
        _, kwargs = mock_mcp.call_args
        assert kwargs["timeout"] == 30
