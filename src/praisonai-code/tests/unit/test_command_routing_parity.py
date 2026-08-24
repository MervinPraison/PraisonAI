"""Routing parity guard for the CLI command registry.

Regression test for the ``search`` drift (issue #4326) and the broader #2191
guarantee that routing can never drift from the advertised command set: every
command surfaced in ``--help`` (``LazyCommandGroup.list_commands``) must also be
recognised by the routing oracle (``get_command_names``), otherwise a real,
registered command is misclassified as a bare prompt and billed as an LLM call.
"""

from praisonai_code.cli import app as app_mod


def test_advertised_commands_are_all_routed():
    group = app_mod.LazyCommandGroup()
    advertised = set(group.list_commands(None))
    routed = app_mod.get_command_names()
    missing = advertised - routed
    assert not missing, f"advertised but not routed: {sorted(missing)}"


def test_search_command_is_routed():
    group = app_mod.LazyCommandGroup()
    assert "search" in group.list_commands(None)
    assert "search" in app_mod.get_command_names()
