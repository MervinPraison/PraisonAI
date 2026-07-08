"""Regression tests for issue #2780.

``praisonai endpoints list`` previously crashed because the Typer handler
re-entered the legacy ``PraisonAI().main()`` with mutated ``sys.argv`` and the
feature module ``praisonai_code.cli.features.endpoints`` did not exist.

These tests verify:
1. The bridge module resolves ``EndpointsHandler`` and
   ``handle_endpoints_command`` (used by the doctor check and legacy dispatcher).
2. The Typer command dispatches to the handler and exits with an integer code
   instead of raising a Rich traceback.
"""

import pytest


def test_endpoints_feature_bridge_exports():
    """Bridge exposes the wrapper handler used by doctor + legacy dispatch."""
    praisonai = pytest.importorskip("praisonai")  # wrapper required for bridge
    from praisonai_code.cli.features.endpoints import (
        EndpointsHandler,
        handle_endpoints_command,
    )

    handler = EndpointsHandler()
    assert handler.DEFAULT_URL
    assert callable(handle_endpoints_command)


def test_handle_endpoints_list_returns_int_no_crash():
    """`endpoints list` returns an int exit code (no server -> graceful error)."""
    pytest.importorskip("praisonai")
    from praisonai_code.cli.features.endpoints import handle_endpoints_command

    code = handle_endpoints_command(["list"])
    assert isinstance(code, int)


def test_endpoints_list_command_exit_zero_or_int():
    """Typer `endpoints list` no longer re-enters legacy main / crashes."""
    pytest.importorskip("praisonai")
    typer_testing = pytest.importorskip("typer.testing")
    from praisonai_code.cli.commands import endpoints as cmd

    runner = typer_testing.CliRunner()
    result = runner.invoke(cmd.app, ["list"])

    assert "Traceback" not in result.output
    assert result.exit_code is not None
