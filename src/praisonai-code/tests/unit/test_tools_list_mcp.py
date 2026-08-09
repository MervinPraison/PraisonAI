"""Tests for MCP server tools appearing in ``praisonai tools list``.

Covers the wrapper feature (#3815) that lets a CLI-first user see the tools
exposed by configured MCP servers alongside built-in / local / external /
registered tools, with lazy, fail-soft discovery.
"""

from unittest import mock

import pytest
from typer.testing import CliRunner

from praisonai_code.cli.commands import tools as tools_cmd


runner = CliRunner()


def _make_tool(name, doc):
    def fn():
        pass

    fn.__name__ = name
    fn.__doc__ = doc
    return fn


class _FakeMCP:
    def __init__(self, tools):
        self._tools = tools

    def __iter__(self):
        return iter(self._tools)


def test_discover_mcp_tools_zero_cost_without_config():
    """No MCP config -> no discovery work, empty result (fail-soft)."""
    import praisonai_code.cli.configuration.resolver as resolver

    with mock.patch.object(resolver, "resolve_config", return_value=object()), \
         mock.patch(
             "praisonai_code.cli.commands.run._collect_mcp_servers_from_config",
             return_value=[],
         ):
        tools, unavailable = tools_cmd._discover_mcp_tools()

    assert tools == {}
    assert unavailable == {}


def test_discover_mcp_tools_groups_and_reports_unavailable():
    """Reachable servers list prefixed tools; unreachable ones get a reason."""
    import praisonai_code.cli.configuration.resolver as resolver

    servers = [
        {"name": "files", "command": "npx"},
        {"name": "broken", "command": "npx"},
    ]

    def fake_create(self, server, timeout=30):
        if server["name"] == "files":
            return _FakeMCP(
                [_make_tool("read", "Read a file"), _make_tool("write", "Write a file")]
            )
        return None

    with mock.patch.object(resolver, "resolve_config", return_value=object()), \
         mock.patch(
             "praisonai_code.cli.commands.run._collect_mcp_servers_from_config",
             return_value=servers,
         ), \
         mock.patch(
             "praisonai_code.cli.features.mcp.MCPHandler.create_mcp_from_server",
             new=fake_create,
         ):
        tools, unavailable = tools_cmd._discover_mcp_tools()

    assert tools == {
        "files_read": "Read a file",
        "files_write": "Write a file",
    }
    assert "broken" in unavailable


def test_list_default_includes_mcp_bucket_and_summary():
    fake = ({"files_read": "Read a file"}, {})
    with mock.patch.object(tools_cmd, "_discover_mcp_tools", return_value=fake):
        result = runner.invoke(tools_cmd.app, ["list"])

    assert result.exit_code == 0, result.output
    assert "files_read" in result.output
    assert "MCP: 1" in result.output


def test_list_source_mcp_shows_only_mcp_and_unavailable():
    fake = ({"files_read": "Read a file"}, {"broken": "timeout"})
    with mock.patch.object(tools_cmd, "_discover_mcp_tools", return_value=fake):
        result = runner.invoke(tools_cmd.app, ["list", "--source", "mcp"])

    assert result.exit_code == 0, result.output
    assert "files_read" in result.output
    assert "Unavailable MCP servers" in result.output
    assert "broken" in result.output


def test_list_other_source_does_not_trigger_mcp_discovery():
    with mock.patch.object(
        tools_cmd, "_discover_mcp_tools", side_effect=AssertionError("called")
    ):
        result = runner.invoke(tools_cmd.app, ["list", "--source", "builtin"])

    assert result.exit_code == 0, result.output
