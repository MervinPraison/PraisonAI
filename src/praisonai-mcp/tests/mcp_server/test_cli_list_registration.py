"""list-resources and list-prompts must register before reading registries.

Regression test for the bug where the listing commands printed empty results on
a fresh process because they read the resource/prompt registries without calling
any registration function first.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout


def _run(command_name: str) -> str:
    from praisonai_mcp.mcp_server.cli import MCPServerCLI

    cli = MCPServerCLI()
    command = getattr(cli, command_name)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = command([])

    assert exit_code == cli.EXIT_SUCCESS
    return buffer.getvalue()


def test_list_resources_registers_before_listing():
    output = _run("cmd_list_resources")
    assert "No resources registered" not in output
    assert "Available MCP Resources" in output


def test_list_prompts_registers_before_listing():
    output = _run("cmd_list_prompts")
    assert "No prompts registered" not in output
    assert "Available MCP Prompts" in output
