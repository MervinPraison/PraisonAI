"""Regression tests for the live standardise CLI surface."""

import pytest

from praisonai.cli.commands import standardise


def test_standardise_module_exposes_only_the_live_cli_entrypoint():
    assert callable(standardise.standardise_command)
    assert not hasattr(standardise, "register_click_commands")


def test_standardise_command_exposes_help_surface(capsys):
    with pytest.raises(SystemExit) as excinfo:
        standardise.standardise_command(["--help"])

    assert excinfo.value.code == 0
    help_output = capsys.readouterr().out
    for subcommand in ("check", "report", "fix", "init"):
        assert subcommand in help_output
