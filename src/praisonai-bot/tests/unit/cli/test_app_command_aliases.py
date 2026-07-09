"""Regression tests for root ``praisonai-bot`` command name resolution (#2842).

Click renders the underscore registry key ``mint_link`` as ``mint-link`` in
``--help`` output, but ``_BotCommandGroup.get_command`` originally only matched
the exact key. That made the advertised hyphen form fail with exit code 2.
These tests assert both hyphen and underscore forms resolve.
"""

import click
from click.testing import CliRunner
from typer.main import get_command as typer_get_command

from praisonai_bot.cli.app import _BotCommandGroup, app

runner = CliRunner()
cli = typer_get_command(app)


def _resolve(cmd_name: str) -> object:
    """Route ``cmd_name`` through the group without importing the sub-app.

    Isolates the hyphen/underscore normalisation logic from the availability
    of optional command modules so the assertion cannot pass vacuously.
    """
    group = _BotCommandGroup(name="praisonai-bot")
    ctx = click.Context(group)
    return group.get_command(ctx, cmd_name)


def test_root_help_lists_hyphenated_mint_link():
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "mint-link" in result.output


def test_list_commands_uses_hyphenated_names():
    group = _BotCommandGroup(name="praisonai-bot")
    names = group.list_commands(click.Context(group))
    assert "mint-link" in names
    assert "mint_link" not in names


def test_root_mint_link_hyphen_resolves():
    command = _resolve("mint-link")
    assert command is not None
    assert command.name == "mint-link"


def test_root_mint_link_underscore_still_resolves():
    command = _resolve("mint_link")
    assert command is not None
    assert command.name == "mint-link"


def test_unknown_command_returns_none():
    assert _resolve("definitely-not-a-command") is None


def test_unknown_command_still_errors():
    result = runner.invoke(cli, ["definitely-not-a-command"])
    assert result.exit_code != 0
