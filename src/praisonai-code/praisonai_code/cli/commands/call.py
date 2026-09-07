"""
Call command group for PraisonAI CLI.

Provides voice/call interaction commands.
"""

from typing import Optional

import typer

app = typer.Typer(help="Voice/call interaction mode")


@app.callback(invoke_without_command=True)
def call_main(
    ctx: typer.Context,
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    public: bool = typer.Option(
        False,
        "--public",
        help="Expose the call server publicly via ngrok (required for inbound PSTN webhooks)",
    ),
    port: Optional[int] = typer.Option(
        None, "--port", help="Port to run the call server on (default: $PORT or 8090)"
    ),
    host: Optional[str] = typer.Option(
        None, "--host", help="Host to bind the call server to (default: 127.0.0.1)"
    ),
):
    """
    Start voice/call interaction mode.

    --public/--port/--host are forwarded to the call server. They were
    previously reachable only through the PUBLIC/PORT environment variables,
    which made inbound PSTN (the one setup that needs a public webhook)
    unreachable from the CLI.

    Examples:
        praisonai call
        praisonai call --model gpt-4o
        praisonai call --public
        praisonai call --host 0.0.0.0 --port 9000
    """
    from praisonai_code._wrapper_bridge import run_wrapper_command

    argv = ['call']
    if model:
        argv.extend(['--model', model])
    if verbose:
        argv.append('--verbose')
    if public:
        argv.append('--public')
    # Only forward when the user actually asked: the call server's own
    # defaults differ from the legacy argparse defaults (PORT/8090 vs 8005),
    # so forwarding unconditionally would silently retarget the port.
    if port is not None:
        argv.extend(['--port', str(port)])
    if host is not None:
        argv.extend(['--host', host])

    run_wrapper_command(argv, feature="call")
