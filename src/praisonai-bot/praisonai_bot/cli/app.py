"""Typer CLI for standalone ``praisonai-bot``."""

from __future__ import annotations

import importlib
from typing import List, Optional

import click
import typer
from typer.core import TyperGroup

_BOT_COMMANDS = {
    "bot": ("praisonai_bot.cli.commands.bot", "app"),
    "gateway": ("praisonai_bot.cli.commands.gateway", "app"),
    "pairing": ("praisonai_bot.cli.commands.pairing", "app"),
    "identity": ("praisonai_bot.cli.commands.identity", "app"),
    "onboard": ("praisonai_bot.cli.commands.onboard", "app"),
    "kanban": ("praisonai_bot.cli.commands.kanban", "app"),
    "claw": ("praisonai_bot.cli.commands.claw", "app"),
    "mint_link": ("praisonai_bot.cli.commands.mint_link", "app"),
}


class _BotCommandGroup(TyperGroup):
    def list_commands(self, ctx: click.Context) -> List[str]:
        return sorted(key.replace("_", "-") for key in _BOT_COMMANDS)

    def get_command(self, ctx: click.Context, cmd_name: str) -> Optional[click.Command]:
        key = cmd_name
        if key not in _BOT_COMMANDS:
            key = cmd_name.replace("-", "_")
        if key not in _BOT_COMMANDS:
            key = cmd_name.replace("_", "-")
        if key not in _BOT_COMMANDS:
            return None
        cmd_name = key
        mod_path, attr = _BOT_COMMANDS[cmd_name]
        try:
            module = importlib.import_module(mod_path)
            sub = getattr(module, attr)
            if isinstance(sub, click.Command):
                return sub
            from typer.main import get_command as typer_get_command

            return typer_get_command(sub)
        except (ImportError, AttributeError) as exc:
            typer.echo(f"Error loading command '{cmd_name}': {exc}", err=True)
            return None


app = typer.Typer(
    cls=_BotCommandGroup,
    name="praisonai-bot",
    help="PraisonAI bots and gateway — messaging channels and WebSocket control plane.",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    """Show help when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()
