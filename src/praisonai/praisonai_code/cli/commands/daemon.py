"""
Daemon command group for PraisonAI CLI.

Lifecycle for the opt-in warm local runtime that keeps provider clients, MCP
connections and recent sessions warm so repeated ``praisonai run`` calls don't
cold-start. ``run`` transparently attaches to a running daemon when present and
falls back to in-process execution otherwise.

    praisonai daemon start     # boot the warm runtime (foreground or background)
    praisonai daemon stop      # stop the running runtime
    praisonai daemon status    # show whether a runtime is up
"""

from typing import Optional

import typer

from praisonai.cli.output.console import get_output_controller

app = typer.Typer(help="Warm local runtime (keeps MCP/provider clients hot)")


@app.command("start")
def daemon_start(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Loopback host to bind"),
    port: int = typer.Option(0, "--port", "-p", help="Port to bind (0 = auto-select)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Default model for warm agents"),
    idle_timeout: float = typer.Option(1800.0, "--idle-timeout", help="Seconds idle before auto-shutdown (0 disables)"),
    background: bool = typer.Option(False, "--background", "-b", help="Detach and run in the background"),
):
    """Start the warm local runtime."""
    output = get_output_controller()

    import ipaddress

    # Local-first: the runtime uses plaintext bearer auth, so it must only ever
    # bind to a loopback interface. Reject anything externally reachable.
    try:
        if not ipaddress.ip_address(host).is_loopback:
            output.print_error("--host must be a loopback address for the local runtime.")
            raise typer.Exit(1)
    except ValueError:
        output.print_error("--host must be a valid loopback IP address.")
        raise typer.Exit(1)

    from praisonai.runtime import get_runtime_descriptor

    existing = get_runtime_descriptor()
    if existing is not None:
        if not existing.is_compatible():
            # A live but version-mismatched runtime is unusable by this client
            # (run/attach skip it via the compat gate). Don't silently report
            # "already running" — that strands the user with an orphan the new
            # client can't talk to. Point them at the explicit fix instead.
            output.print_error(
                f"A runtime is running at {existing.base_url} (pid {existing.pid}) but "
                f"speaks an incompatible version (v{existing.version or '?'}). "
                "Stop it first with: praisonai daemon stop"
            )
            raise typer.Exit(1)
        output.print_warning(
            f"Runtime already running at {existing.base_url} (pid {existing.pid})."
        )
        raise typer.Exit(0)

    if background:
        import subprocess
        import sys

        cmd = [
            sys.executable, "-m", "praisonai.runtime",
            "--host", host,
            "--port", str(port),
            "--idle-timeout", str(idle_timeout),
        ]
        if model:
            cmd.extend(["--model", model])
        # Detach: the child writes the lockfile once it is bound.
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Give the child a moment to bind and write the descriptor.
        import time

        for _ in range(50):
            time.sleep(0.1)
            descriptor = get_runtime_descriptor()
            if descriptor is not None:
                output.print_success(
                    f"Warm runtime started in background at {descriptor.base_url} (pid {descriptor.pid})."
                )
                raise typer.Exit(0)
        # Readiness timed out: don't leave an orphaned child running silently.
        try:
            proc.terminate()
        except OSError:
            pass
        output.print_error("Runtime did not report ready in time.")
        raise typer.Exit(1)

    output.print_info(f"Starting warm runtime on {host}:{port or 'auto'} (Ctrl-C to stop)...")
    try:
        from praisonai.runtime.server import serve_runtime

        serve_runtime(host=host, port=port, model=model, idle_timeout=idle_timeout)
    except KeyboardInterrupt:
        output.print_info("Runtime stopped.")
    except Exception as e:  # noqa: BLE001
        output.print_error(f"Failed to start runtime: {e}")
        raise typer.Exit(1)


@app.command("stop")
def daemon_stop():
    """Stop the running warm runtime."""
    output = get_output_controller()

    from praisonai.runtime import RuntimeClient, get_runtime_descriptor
    from praisonai.runtime.descriptor import RuntimeDescriptor

    descriptor = get_runtime_descriptor()
    if descriptor is None:
        output.print_info("No warm runtime is running.")
        raise typer.Exit(0)

    # Verify the recorded pid still belongs to *our* runtime before signalling.
    # After PID reuse the lockfile pid could point at an unrelated process, so a
    # failed health check is treated as a stale lockfile rather than a SIGTERM.
    if not RuntimeClient(descriptor, timeout=2.0).ping():
        output.print_info("Runtime descriptor is stale; cleaning up lockfile.")
        RuntimeDescriptor.remove()
        raise typer.Exit(0)

    import os
    import signal

    try:
        os.kill(descriptor.pid, signal.SIGTERM)
        output.print_success(f"Stopped warm runtime (pid {descriptor.pid}).")
    except ProcessLookupError:
        output.print_info("Runtime process already gone; cleaning up lockfile.")
    except OSError as e:
        output.print_error(f"Failed to stop runtime: {e}")
        raise typer.Exit(1) from e
    finally:
        RuntimeDescriptor.remove()


@app.command("status")
def daemon_status(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Show whether a warm runtime is running."""
    output = get_output_controller()

    from praisonai.runtime import get_runtime_descriptor

    descriptor = get_runtime_descriptor()
    running = descriptor is not None

    if json_output:
        import json

        payload = {"running": running}
        if descriptor is not None:
            payload.update({
                "host": descriptor.host,
                "port": descriptor.port,
                "pid": descriptor.pid,
                "base_url": descriptor.base_url,
                "version": descriptor.version,
                "compatible": descriptor.is_compatible(),
            })
        print(json.dumps(payload))
        return

    if running:
        compat = "" if descriptor.is_compatible() else " [version mismatch]"
        output.print_success(
            f"Warm runtime running at {descriptor.base_url} "
            f"(pid {descriptor.pid}, v{descriptor.version or '?'}){compat}."
        )
    else:
        output.print_info("No warm runtime is running.")


@app.callback(invoke_without_command=True)
def daemon_main(ctx: typer.Context):
    """Manage the warm local runtime."""
    if ctx.invoked_subcommand is None:
        output = get_output_controller()
        output.print_panel(
            "Warm local runtime keeps provider clients and MCP connections hot\n"
            "so repeated `praisonai run` calls skip cold-start.\n\n"
            "Usage:\n"
            "  praisonai daemon start [--background]\n"
            "  praisonai daemon stop\n"
            "  praisonai daemon status\n",
            title="Daemon (warm runtime)",
        )
