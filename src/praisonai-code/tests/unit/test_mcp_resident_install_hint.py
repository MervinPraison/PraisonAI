"""``praisonai connect`` / ``praisonai mcp`` without praisonai-mcp installed.

praisonai-code does not depend on praisonai-mcp. Typed by name, an MCP
command must print a one-line install hint and exit 1: no traceback, no
"No such command", and it stays out of ``--help``.
"""

import pytest
from typer.testing import CliRunner

from praisonai_code.cli import app as cli_app


@pytest.mark.parametrize("name", sorted(cli_app._MCP_RESIDENT_COMMANDS))
def test_missing_praisonai_mcp_prints_an_install_hint(monkeypatch, name):
    monkeypatch.setattr(cli_app, "mcp_package_available", lambda: False)
    result = CliRunner().invoke(cli_app.app, [name, "cursor", "--all"])
    assert result.exit_code == 1
    assert "pip install praisonai-mcp" in result.output
    assert "Traceback" not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_mcp_commands_stay_out_of_help_without_the_package(monkeypatch):
    import typer.main

    monkeypatch.setattr(cli_app, "mcp_package_available", lambda: False)
    names = typer.main.get_command(cli_app.app).list_commands(None)
    assert not set(cli_app._MCP_RESIDENT_COMMANDS) & set(names)
