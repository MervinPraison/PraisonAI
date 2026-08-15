"""Regression: ``praisonai gateway`` and ``praisonai-bot gateway`` share one surface.

The public ``praisonai gateway <cmd>`` entry point used to route through a
reduced argparse handler that only wired ``start``/``status``/``hooks`` and
dead-ended on everything else — even though the gateway's own degraded-state
retry hints tell operators to run ``praisonai gateway doctor``/``test`` (#3966).

These tests pin the unified behaviour: the public list-args handler dispatches
to the single canonical Typer command app, so the two entry points advertise
the same subcommands and ``gateway doctor`` resolves rather than printing
``Unknown gateway command: doctor``.
"""

from __future__ import annotations

import click

from praisonai_bot.cli.commands.gateway import app as gateway_app
from praisonai_bot.cli.features.gateway import handle_gateway_command


def _canonical_subcommands() -> set[str]:
    from typer.main import get_command

    command = get_command(gateway_app)
    return set(command.list_commands(click.Context(command)))


def test_public_and_canonical_expose_same_gateway_surface():
    """The full operational command set is reachable from ``praisonai gateway``."""
    surface = _canonical_subcommands()
    # Every operational verb the issue enumerates must be present on the single
    # canonical app the public handler now routes to.
    for cmd in (
        "start", "status", "stop", "restart", "doctor", "test", "channels",
        "pause", "resume", "reconnect", "install", "uninstall", "mint-link",
        "logs", "send", "hooks", "sessions",
    ):
        assert cmd in surface, f"missing gateway subcommand: {cmd}"


def test_gateway_doctor_resolves_from_public_handler():
    """``praisonai gateway doctor`` resolves instead of dead-ending (#3966)."""
    # ``--help`` exercises the routing/parse path without running diagnostics.
    rc = handle_gateway_command(["doctor", "--help"])
    assert rc == 0


def test_gateway_start_exposes_openai_and_mcp_flags():
    """The public ``start`` is the canonical safe ``start`` with compat surfaces.

    The reduced argparse ``start`` omitted ``--openai-api``/``--mcp``; routing to
    the canonical app means the public ``start`` now advertises them (#3966).
    """
    from typer.main import get_command

    command = get_command(gateway_app)
    start = command.get_command(click.Context(command), "start")
    opts = [opt for param in start.params for opt in param.opts]
    assert "--openai-api" in opts
    assert "--mcp" in opts


def test_unknown_gateway_command_no_longer_dead_ends(capsys):
    """An unknown verb yields a non-zero code, not the old static dead-end."""
    rc = handle_gateway_command(["definitely-not-a-command"])
    assert rc != 0
    combined = capsys.readouterr()
    assert "Available commands: start, status, hooks" not in (
        combined.out + combined.err
    )
