"""Regression tests for the live standardise CLI surface."""

from praisonai.cli.commands import standardise


def test_standardise_module_exposes_only_the_live_cli_entrypoint():
    assert callable(standardise.standardise_command)
    assert not hasattr(standardise, "register_click_commands")
