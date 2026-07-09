"""Regression tests for root ``praisonai-bot`` command name resolution (#2842).

Click renders the underscore registry key ``mint_link`` as ``mint-link`` in
``--help`` output, but ``_BotCommandGroup.get_command`` originally only matched
the exact key. That made the advertised hyphen form fail with exit code 2.
These tests assert both hyphen and underscore forms resolve.
"""

from click.testing import CliRunner
from typer.main import get_command as typer_get_command

from praisonai_bot.cli.app import app

runner = CliRunner()
cli = typer_get_command(app)


def test_root_help_lists_hyphenated_mint_link():
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "mint-link" in result.output


def test_root_mint_link_hyphen_resolves():
    result = runner.invoke(cli, ["mint-link", "--help"])
    assert result.exit_code == 0


def test_root_mint_link_underscore_still_resolves():
    result = runner.invoke(cli, ["mint_link", "--help"])
    assert result.exit_code == 0


def test_unknown_command_still_errors():
    result = runner.invoke(cli, ["definitely-not-a-command"])
    assert result.exit_code != 0
