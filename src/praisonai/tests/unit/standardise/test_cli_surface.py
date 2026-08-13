"""Regression tests for the live standardise CLI surface."""

import pytest
from typer.testing import CliRunner

from praisonai.cli.commands import standardise
from praisonai_code.cli.app import app


def test_standardise_module_exposes_only_the_live_cli_entrypoint():
    assert callable(standardise.standardise_command)
    assert not hasattr(standardise, "register_click_commands")


@pytest.mark.parametrize("alias", ["standardise", "standardize"])
def test_public_standardise_aliases_expose_live_help(alias):
    result = CliRunner(env={"NO_COLOR": "1"}).invoke(
        app, [alias, "--help"], color=False
    )

    assert result.exit_code == 0, result.output
    assert "check" in result.output
    assert "report" in result.output
