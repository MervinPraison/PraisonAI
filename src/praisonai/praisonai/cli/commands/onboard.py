"""
Onboard command group for PraisonAI CLI.

Provides the bot onboarding wizard command.
"""

import os

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Messaging bot onboarding (platforms, tokens, daemon)")


def run_onboard() -> None:
    """Run onboarding with lazy import."""
    from ..features.onboard import run_onboard as _run_onboard
    _run_onboard()


@app.callback(invoke_without_command=True)
def onboard_callback(
    ctx: typer.Context,
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        "--non-interactive",
        help=(
            "Non-interactive mode: skip all prompts and accept defaults. "
            "Tokens/allowlists are taken from existing env vars; missing "
            "values are left blank. Equivalent to PRAISONAI_NO_PROMPT=1."
        ),
    ),
):
    """Run the bot onboarding wizard."""
    if ctx.invoked_subcommand:
        return
    if yes:
        # Propagate to run_onboard() and any subprocesses it spawns.
        # Intentionally not restored afterwards: the CLI is a one-shot entrypoint.
        os.environ["PRAISONAI_NO_PROMPT"] = "1"
    try:
        run_onboard()
    except KeyboardInterrupt:
        get_output_controller().print_info("Cancelled.")
        raise typer.Exit(130)
