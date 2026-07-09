"""Regression tests for issue #2841.

``praisonai-code eval list`` must resolve as an alias for ``eval list-judges``
instead of failing with a Typer "No such command 'list'" error (exit code 2).
"""

from typer.testing import CliRunner

from praisonai_code.cli.commands.eval import app


def test_eval_list_not_unknown_subcommand():
    result = CliRunner().invoke(app, ["list"])
    assert result.exit_code != 2
    assert "Registered Judge Types" in result.output


def test_eval_list_judges_unchanged():
    result = CliRunner().invoke(app, ["list-judges"])
    assert result.exit_code == 0
    assert "Registered Judge Types" in result.output


def test_eval_help_documents_list():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "list" in result.output
