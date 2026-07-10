"""Tests for grouped, categorised CLI ``--help`` panels (issue #2865).

``praisonai --help`` must present its commands in a small number of stable,
discoverable panels instead of one flat ~90-item list. Grouping is data-driven
(the :mod:`praisonai_code.cli.help_categories` map is the single source of
truth) and every advertised command must map to a category so nothing is ever
hidden.
"""

import click
from typer.main import get_command
from typer.testing import CliRunner

from praisonai_code.cli.app import app, _LAZY_COMMANDS, _SPECIAL_COMMANDS
from praisonai_code.cli.help_categories import (
    CATEGORIES,
    DEFAULT_CATEGORY,
    COMMAND_CATEGORIES,
    category_for,
)


def _root_context() -> click.Context:
    command = get_command(app)
    return click.Context(command, info_name="praisonai")


def test_every_registered_command_has_a_category():
    """No advertised command may fall through to an unknown category.

    Uncategorised commands still resolve to ``DEFAULT_CATEGORY`` at runtime, but
    we assert every registry command is *explicitly* mapped so new commands opt
    into a category deliberately at registration time.
    """
    registered = set(_LAZY_COMMANDS) | set(_SPECIAL_COMMANDS)
    # Advertised inline/dynamic commands not present in the registries.
    registered.update({"app", "standardise", "standardize", "index", "query", "search"})

    missing = sorted(n for n in registered if n not in COMMAND_CATEGORIES)
    assert not missing, f"commands without a help category: {missing}"


def test_category_for_falls_back_to_default():
    assert category_for("run") in CATEGORIES
    assert category_for("a-command-that-does-not-exist") == DEFAULT_CATEGORY


def test_all_mapped_categories_are_canonical():
    for name, category in COMMAND_CATEGORIES.items():
        assert category in CATEGORIES, (
            f"command {name!r} mapped to unknown category {category!r}"
        )


def test_core_commands_are_signposted():
    """The everyday first-run path must be easy to find."""
    from praisonai_code.cli.help_categories import CATEGORY_GET_STARTED, CATEGORY_RUN_CHAT

    assert category_for("init") == CATEGORY_GET_STARTED
    assert category_for("setup") == CATEGORY_GET_STARTED
    assert category_for("run") == CATEGORY_RUN_CHAT
    assert category_for("chat") == CATEGORY_RUN_CHAT


def test_get_command_tags_help_panel():
    """Resolved commands carry their category as Typer's ``rich_help_panel``."""
    ctx = _root_context()
    root = ctx.command
    for name, expected in (("run", "Run & chat"), ("init", "Get started")):
        cmd = root.get_command(ctx, name)
        assert cmd is not None
        assert cmd.rich_help_panel == expected


def test_help_output_is_grouped_not_flat():
    """The rendered help groups commands into categorised panels."""
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    # At least a couple of the category panel titles must appear.
    assert "Get started" in result.output
    assert "Run & chat" in result.output


def test_help_still_exits_zero():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
