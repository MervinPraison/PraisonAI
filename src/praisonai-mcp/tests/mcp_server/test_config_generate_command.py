"""
Tests for ``config-generate`` STDIO command resolution.

Standalone installs (``pip install praisonai-mcp``) expose only the
``praisonai-mcp`` entry point, which accepts ``serve`` directly. Umbrella
installs (``pip install praisonai``) expose ``praisonai``, which requires the
``mcp serve`` subcommand. The generated MCP client config must match whichever
entry point is available. See issue #3210.
"""

from argparse import Namespace

import pytest

from praisonai_mcp.mcp_server.cli import MCPServerCLI
from praisonai_mcp.mcp_server.recipe_cli import RecipeMCPCLI


def _stdio_args():
    return Namespace(transport="stdio", host="127.0.0.1", port=8080)


@pytest.fixture
def cli():
    return MCPServerCLI()


def test_standalone_install_uses_praisonai_mcp(cli, monkeypatch):
    monkeypatch.setattr(
        "praisonai_mcp.mcp_server.cli.shutil.which",
        lambda name: "/usr/bin/praisonai-mcp" if name == "praisonai-mcp" else None,
    )
    command, args = cli._stdio_command()
    assert command == "praisonai-mcp"
    assert args == ["serve", "--transport", "stdio"]


def test_umbrella_install_uses_praisonai(cli, monkeypatch):
    monkeypatch.setattr(
        "praisonai_mcp.mcp_server.cli.shutil.which",
        lambda name: None,
    )
    command, args = cli._stdio_command()
    assert command == "praisonai"
    assert args == ["mcp", "serve", "--transport", "stdio"]


@pytest.mark.parametrize(
    "generator, key",
    [
        ("_generate_claude_desktop_config", "mcpServers"),
        ("_generate_cursor_config", "mcpServers"),
        ("_generate_vscode_config", "mcp.servers"),
        ("_generate_windsurf_config", "mcpServers"),
    ],
)
def test_standalone_all_clients(cli, monkeypatch, generator, key):
    monkeypatch.setattr(
        "praisonai_mcp.mcp_server.cli.shutil.which",
        lambda name: "/usr/bin/praisonai-mcp" if name == "praisonai-mcp" else None,
    )
    config = getattr(cli, generator)(_stdio_args())
    server = config[key]["praisonai"]
    assert server["command"] == "praisonai-mcp"
    assert server["args"] == ["serve", "--transport", "stdio"]
    assert "mcp" not in server["args"]


@pytest.mark.parametrize(
    "generator, key",
    [
        ("_generate_claude_desktop_config", "mcpServers"),
        ("_generate_cursor_config", "mcpServers"),
        ("_generate_vscode_config", "mcp.servers"),
        ("_generate_windsurf_config", "mcpServers"),
    ],
)
def test_umbrella_all_clients(cli, monkeypatch, generator, key):
    monkeypatch.setattr(
        "praisonai_mcp.mcp_server.cli.shutil.which",
        lambda name: None,
    )
    config = getattr(cli, generator)(_stdio_args())
    server = config[key]["praisonai"]
    assert server["command"] == "praisonai"
    assert server["args"] == ["mcp", "serve", "--transport", "stdio"]


@pytest.fixture
def recipe_cli():
    return RecipeMCPCLI()


def test_recipe_standalone_uses_praisonai_mcp(recipe_cli, monkeypatch):
    monkeypatch.setattr(
        "praisonai_mcp.mcp_server.recipe_cli.shutil.which",
        lambda name: "/usr/bin/praisonai-mcp" if name == "praisonai-mcp" else None,
    )
    command, args = recipe_cli._stdio_recipe_command("support-reply")
    assert command == "praisonai-mcp"
    assert args == ["serve-recipe", "support-reply", "--transport", "stdio"]
    assert "mcp" not in args


def test_recipe_umbrella_uses_praisonai(recipe_cli, monkeypatch):
    monkeypatch.setattr(
        "praisonai_mcp.mcp_server.recipe_cli.shutil.which",
        lambda name: None,
    )
    command, args = recipe_cli._stdio_recipe_command("support-reply")
    assert command == "praisonai"
    assert args == ["mcp", "serve-recipe", "support-reply", "--transport", "stdio"]
