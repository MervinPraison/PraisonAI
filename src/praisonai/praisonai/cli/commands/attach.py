"""
Attach command for PraisonAI CLI.

Subscribe to a live session running on the warm local runtime and stream its
events in real time from another terminal. Multiple clients can attach to the
same active session and observe it concurrently.

    praisonai attach <session-id>

The runtime must be running (``praisonai daemon start``) and a ``praisonai run``
must have been issued against the same session id (``run --attach <id>``) for
events to appear. Attaching is read-only: it never starts execution itself.
"""

import json as _json

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Attach to a live session on the warm runtime")


@app.callback(invoke_without_command=True)
def attach_main(
    ctx: typer.Context,
    session_id: str = typer.Argument(..., help="Session id to attach to"),
    json_output: bool = typer.Option(False, "--json", help="Emit raw NDJSON events"),
):
    """Stream live events for a running session.

    Examples:
        praisonai attach my-session
        praisonai attach my-session --json
    """
    if ctx.invoked_subcommand is not None:
        return

    output = get_output_controller()

    try:
        from ...runtime import (
            get_runtime_descriptor,
            RuntimeClient,
            RuntimeUnavailable,
        )
    except ImportError as e:
        output.print_error(f"Runtime module not available: {e}")
        raise typer.Exit(4)

    # Require a compatible runtime (same major version) so we never attach to an
    # older runtime that lacks /sessions/{id}/events or speaks a different event
    # contract — mirrors the gate the `run` path uses before reusing a runtime.
    descriptor = get_runtime_descriptor(require_compatible=True)
    if descriptor is None:
        output.print_error(
            "No compatible warm runtime is running. Start one with: praisonai daemon start"
        )
        raise typer.Exit(1)

    client = RuntimeClient(descriptor)

    if not json_output:
        output.print_info(f"Attached to session '{session_id}'. Ctrl-C to detach.")

    try:
        for event in client.attach(session_id):
            if json_output:
                print(_json.dumps(event), flush=True)
                continue
            _render_event(output, event)
    except RuntimeUnavailable as e:
        output.print_error(f"Lost connection to runtime: {e}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        if not json_output:
            output.print_info("Detached.")
        raise typer.Exit(0)


def _render_event(output, event: dict) -> None:
    """Render a single session event for human-readable terminals."""
    etype = event.get("type", "event")
    if etype == "run.start":
        prompt = event.get("prompt", "")
        output.print_info(f"▶ run.start: {prompt}")
    elif etype == "run.result":
        result = event.get("result", "")
        output.print_success("✓ run.result")
        if result:
            print(result)
    elif etype == "run.error":
        output.print_error(f"✗ run.error: {event.get('error', '')}")
    else:
        output.print(_json.dumps(event))
