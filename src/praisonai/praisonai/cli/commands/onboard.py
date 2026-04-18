"""
Onboard command group for PraisonAI CLI.

Provides the bot onboarding wizard command.
"""

import typer
from ..output.console import get_output_controller

app = typer.Typer(help="Messaging bot onboarding (platforms, tokens, daemon)")

@app.callback(invoke_without_command=True)
def onboard_callback(ctx: typer.Context):
    """Run the bot onboarding wizard."""
    if ctx.invoked_subcommand:
        return
    from ..features.onboard import run_onboard
    try:
        run_onboard()
    except KeyboardInterrupt:
        get_output_controller().print_info("Cancelled.")
        raise typer.Exit(130)