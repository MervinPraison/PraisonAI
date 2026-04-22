"""
Realtime command group for PraisonAI CLI.

Provides realtime interaction commands.
"""

from typing import Optional

import typer

app = typer.Typer(help="Realtime interaction mode")


@app.callback(invoke_without_command=True)
def realtime_main(
    ctx: typer.Context,
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    port: int = typer.Option(8085, "--port", "-p", help="Port for realtime UI"),
):
    """
    Start realtime interaction mode.
    
    Now routes to the new aiui-based realtime interface.
    
    Examples:
        praisonai realtime
        praisonai realtime --model gpt-4o --port 9000
    """
    import os
    
    if model:
        os.environ["MODEL_NAME"] = model
    
    print("🎤 Launching PraisonAI Realtime Voice Interface...")
    print("Note: Migrated from Chainlit to aiui.")

    try:
        from praisonai.cli.commands.ui import _launch_aiui_app
        _launch_aiui_app(
            app_dir="ui_realtime",
            default_app_name="ui_realtime",
            port=port,
            host="127.0.0.1",
            app_file=None,
            reload=False,
            ui_name="Realtime Voice"
        )
    except ImportError:
        print('\033[91mERROR: Realtime UI is not installed.\033[0m')
        print('Install with: pip install "praisonai[ui]"')
        raise typer.Exit(1)
