"""Tests for MCP cold-start timeout auto-extension (issue #5099).

On a fresh cache, package launchers such as ``npx``/``uvx`` must download the
MCP server before the handshake begins, which routinely exceeds the 60s default
init timeout. The MCP class raises the effective default to ``COLD_START_TIMEOUT``
for these launchers, while leaving an explicit caller-provided timeout untouched.
"""

import pytest

from praisonaiagents.mcp.mcp import MCP


class TestColdStartLauncherDetection:
    """The launcher classifier that drives the timeout bump."""

    @pytest.mark.parametrize("cmd", [
        "npx", "uvx", "bunx", "pnpm", "yarn",
        "/usr/local/bin/npx", "C:\\Program Files\\nodejs\\npx.cmd",
        "npx.exe", "NPX.CMD",
    ])
    def test_launchers_detected(self, cmd):
        assert MCP._is_cold_start_launcher(cmd) is True

    @pytest.mark.parametrize("cmd", [
        "python", "node", "/usr/bin/python3",
        "server-filesystem", "my-npx-tool", None, 123,
    ])
    def test_non_launchers_ignored(self, cmd):
        assert MCP._is_cold_start_launcher(cmd) is False


class TestColdStartTimeoutConstants:
    """The two default tiers are distinct and ordered."""

    def test_cold_start_is_larger_than_default(self):
        assert MCP.COLD_START_TIMEOUT > MCP.DEFAULT_TIMEOUT
        assert MCP.DEFAULT_TIMEOUT == 60
        assert MCP.COLD_START_TIMEOUT == 180
