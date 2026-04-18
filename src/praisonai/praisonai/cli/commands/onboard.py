"""
Onboard command group for PraisonAI CLI.

Provides the bot onboarding wizard command.
"""

import typer
from ..output.console import get_output_controller

app = typer.Typer(help="Messaging bot onboarding (platforms, tokens, daemon)")


def run_onboard() -> None:
    """Run onboarding with lazy import."""
    from ..features.onboard import run_onboard as _run_onboard
    _run_onboard()


@app.callback(invoke_without_command=True)
def onboard_callback(ctx: typer.Context):
    """Run the bot onboarding wizard."""
    if ctx.invoked_subcommand:
        return
    try:
        run_onboard()
    except KeyboardInterrupt:
        get_output_controller().print_info("Cancelled.")
        raise typer.Exit(130)
