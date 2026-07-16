"""C12 backward-compat: praisonai.mcp_server shims alias praisonai_mcp."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
MCP_PKG = REPO / "src" / "praisonai-mcp"
WRAPPER_PKG = REPO / "src" / "praisonai"


@pytest.fixture(autouse=True)
def _bootstrap_paths():
    for p in (
        str(REPO / "src" / "praisonai-agents"),
        str(MCP_PKG),
        str(WRAPPER_PKG),
        str(REPO / "src" / "praisonai-code"),
    ):
        if p not in sys.path:
            sys.path.insert(0, p)
    from praisonai._bootstrap import ensure_praisonai_code, ensure_praisonai_mcp

    ensure_praisonai_mcp()
    ensure_praisonai_code()
    yield


class TestMcpModuleIdentity:
    @pytest.mark.parametrize(
        "old,new",
        [
            ("praisonai.mcp_server.server", "praisonai_mcp.mcp_server.server"),
            ("praisonai.mcp_server.registry", "praisonai_mcp.mcp_server.registry"),
            ("praisonai.mcp_server.cli", "praisonai_mcp.mcp_server.cli"),
        ],
    )
    def test_module_identity(self, old: str, new: str):
        old_mod = importlib.import_module(old)
        new_mod = importlib.import_module(new)
        assert old_mod is new_mod

    def test_mcp_server_class_identity(self):
        from praisonai.mcp_server import MCPServer as OldServer
        from praisonai_mcp.mcp_server.server import MCPServer as NewServer

        assert OldServer is NewServer

    def test_cli_shim_app_identity(self):
        old_mod = importlib.import_module("praisonai.cli.commands.mcp")
        new_mod = importlib.import_module("praisonai_mcp.cli.commands.mcp")
        assert old_mod is new_mod

    def test_no_nested_shadow_package(self):
        nested = WRAPPER_PKG / "praisonai" / "praisonai_mcp"
        assert not nested.exists()


class TestMcpCliRouting:
    def test_mcp_resident_commands_declared(self):
        from praisonai_code.cli import app as code_app

        assert "mcp" in code_app._MCP_RESIDENT_COMMANDS
        assert "mcp" not in code_app._WRAPPER_RESIDENT_COMMANDS

    def test_mcp_bridge_available(self):
        from praisonai_code._mcp_bridge import mcp_package_available

        assert mcp_package_available() is True

    def test_get_command_resolves_mcp(self):
        import click
        from praisonai_code.cli.app import app  # noqa: F401
        from typer.main import get_command as typer_get_command

        root = typer_get_command(app)
        ctx = click.Context(root)
        cmd = root.get_command(ctx, "mcp")
        assert cmd is not None
