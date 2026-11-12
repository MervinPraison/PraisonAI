"""`praisonai flow export --format` must work on every supported Typer.

Typer 0.28 removed ``Option(click_type=...)``; the old declaration raised
TypeError while building the CLI, which broke every ``praisonai --help``.
"""

from typer.testing import CliRunner

from praisonai.cli.commands.flow import app

runner = CliRunner()


def test_export_help_builds():
    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0, result.output
    assert "--format" in result.output


def test_export_rejects_unknown_format():
    result = runner.invoke(app, ["export", "abc", "--format", "xml"])
    assert result.exit_code == 2
    assert "yaml" in result.output
