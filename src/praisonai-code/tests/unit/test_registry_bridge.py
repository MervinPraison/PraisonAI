"""Regression tests for issue #2820.

``praisonai registry list`` / ``registry serve`` previously crashed because the
Typer handlers re-entered the legacy ``PraisonAI().main()`` with mutated
``sys.argv`` and the feature module
``praisonai_code.cli.features.registry`` did not exist (``RegistryHandler`` was
never bridged into praisonai-code).

These tests verify:
1. The bridge module resolves ``RegistryHandler`` and
   ``handle_registry_command`` (used by ``serve registry`` and legacy dispatch).
2. The Typer commands dispatch to the handler and exit with an integer code
   instead of raising a Rich traceback.
"""

import pytest


def test_registry_feature_bridge_exports():
    """Bridge exposes the wrapper handler used by serve + legacy dispatch."""
    pytest.importorskip("praisonai")  # wrapper required for bridge
    from praisonai_code.cli.features.registry import (
        RegistryHandler,
        handle_registry_command,
    )

    handler = RegistryHandler()
    assert callable(handler.handle)
    assert callable(handler.cmd_list)
    assert callable(handler.cmd_serve)
    assert callable(handle_registry_command)


def test_handle_registry_list_returns_int_no_crash():
    """`registry list` returns an int exit code (empty registry -> graceful)."""
    pytest.importorskip("praisonai")
    from praisonai_code.cli.features.registry import handle_registry_command

    code = handle_registry_command(["list"])
    assert isinstance(code, int)


def test_registry_list_command_exit_int_no_traceback():
    """Typer `registry list` no longer re-enters legacy main / crashes."""
    pytest.importorskip("praisonai")
    typer_testing = pytest.importorskip("typer.testing")
    from praisonai_code.cli.commands import registry as cmd

    runner = typer_testing.CliRunner()
    result = runner.invoke(cmd.app, ["list"])

    assert "Traceback" not in result.output
    assert "ModuleNotFoundError" not in result.output
    assert isinstance(result.exit_code, int)


def test_serve_registry_no_import_error():
    """`serve registry --help` resolves without ImportError (exit 4)."""
    pytest.importorskip("praisonai")
    typer_testing = pytest.importorskip("typer.testing")
    from praisonai_code.cli.commands import serve as cmd

    runner = typer_testing.CliRunner()
    result = runner.invoke(cmd.app, ["registry", "--help"])

    assert result.exit_code == 0
    assert "Registry module not available" not in result.output
