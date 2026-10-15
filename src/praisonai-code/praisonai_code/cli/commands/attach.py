"""
Attach command for PraisonAI CLI.

Subscribe to a live session running on the warm local runtime and stream its
events in real time from another terminal. Multiple clients can attach to the
same active session and observe it concurrently.

    praisonai attach <session-id>

The runtime must be running (``praisonai daemon start``) and a ``praisonai run``
must have been issued against the same session id (``run --attach <id>``) for
events to appear. Attaching is read-only by default: it never starts execution
itself. ``--message`` steers and ``--interrupt`` cancels the live turn instead:

    praisonai attach --message "also update the tests" <session-id>
    praisonai attach --interrupt <session-id>
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
    message: str = typer.Option(
        None, "--message", "-m", help="Steer the live turn with this message, then exit"
    ),
    interrupt: bool = typer.Option(
        False, "--interrupt", help="Interrupt the live turn, then exit"
    ),
):
    """Stream live events for a running session.

    Examples:
        praisonai attach my-session
        praisonai attach my-session --json
        praisonai attach -m "focus on the failing test" my-session
        praisonai attach --interrupt my-session
    """
    if ctx.invoked_subcommand is not None:
        return

    output = get_output_controller()

    try:
        from praisonai_code.runtime import (
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

    if message or interrupt:
        try:
            if message:
                client.steer(session_id, message)
                output.print_success(f"Steering message sent to '{session_id}'.")
            if interrupt:
                client.interrupt(session_id)
                output.print_success(f"Interrupt requested for '{session_id}'.")
        except RuntimeUnavailable as e:
            output.print_error(str(e))
            raise typer.Exit(1)
        return

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
    elif etype == "run.steer":
        output.print_info(f"↪ run.steer: {event.get('message', '')}")
    elif etype == "run.interrupt":
        output.print_info("■ run.interrupt requested")
    else:
        output.print(_json.dumps(event))
