"""``praisonai-train remote`` — train on another machine over SSH.

`praisonai_train/remote/runner.py` has been a complete implementation of this
for some time — preflight, ship, detached start, log tail, fetch, stop — with
**zero call sites**. Nothing outside its own package imported it, so the one
capability unsloth has no counterpart for could not be reached from the CLI.

    praisonai-train remote preflight gpubox
    praisonai-train remote start gpubox -c config.yaml -d data/train.jsonl
    praisonai-train remote tail gpubox run-1787... 
    praisonai-train remote fetch gpubox run-1787... lora_model -o ./out
    praisonai-train remote stop gpubox run-1787...

The run id is printed by `start` and accepted by the rest. Runs survive the
SSH session, so a dropped laptop connection does not kill the training.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from praisonai_train.cli.commands.train import app

remote_app = typer.Typer(
    help="Train on a remote GPU host over SSH.", no_args_is_help=True)
app.add_typer(remote_app, name="remote")


def _out():
    """The shared output controller, matching every other command module."""
    from praisonai_train.cli.output.console import get_output_controller
    return get_output_controller()


def _runner(host: str, python: str, workdir: str):
    from praisonai_train.remote.runner import RemoteRunner
    return RemoteRunner(alias=host, python=python, workdir=workdir)


def _run_handle(host: str, run_id: str, workdir: str):
    from praisonai_train.remote.runner import RemoteRun
    base = workdir.rstrip("/")
    remote_dir = f"{base}/{run_id}"
    return RemoteRun(host=host, run_id=run_id, remote_dir=remote_dir,
                     log_path=f"{remote_dir}/train.log")


@remote_app.command("preflight")
def preflight(
    host: str = typer.Argument(..., help="SSH alias, as in ~/.ssh/config."),
    gpus: int = typer.Option(1, "--gpus", help="How many GPUs the host must have."),
    python: str = typer.Option("python3", "--python"),
    workdir: str = typer.Option("~/.praisonai-train", "--workdir"),
    as_json: bool = typer.Option(False, "--json", "-j"),
):
    """Check the host can train, before shipping anything to it."""
    result = _runner(host, python, workdir).preflight(expect_gpus=gpus)
    if as_json:
        typer.echo(json.dumps({
            "host": host, "ok": result.ok,
            "why_not": None if result.ok else result.why_not(),
        }, indent=2))
        # A machine-readable "not ready" must still exit non-zero, or a script
        # reading only the exit status ships a job to a box that cannot run it.
        if not result.ok:
            raise typer.Exit(1)
    elif result.ok:
        _out().print_success(f"{host} is ready to train.")
    else:
        # Not an exception: "this host is not ready" is an answer, and the
        # reason is the useful part.
        _out().print_error(f"{host} cannot train", remediation=result.why_not())
        raise typer.Exit(1)


@remote_app.command("start")
def start(
    host: str = typer.Argument(..., help="SSH alias, as in ~/.ssh/config."),
    config: Path = typer.Option(..., "--config", "-c", exists=True,
                                help="Training config to ship."),
    dataset: Optional[Path] = typer.Option(None, "--dataset", "-d", exists=True,
                                           help="Local dataset to ship alongside it."),
    gpus: int = typer.Option(1, "--gpus"),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    python: str = typer.Option("python3", "--python"),
    workdir: str = typer.Option("~/.praisonai-train", "--workdir"),
    follow: bool = typer.Option(True, "--follow/--no-follow",
                                help="Stream the log until the run ends."),
):
    """Ship the job and start it. The run outlives this command."""
    runner = _runner(host, python, workdir)
    from praisonai_train.remote.runner import RemoteError
    try:
        run = runner.start(config_path=config, dataset_path=dataset,
                           run_id=run_id, expect_gpus=gpus)
    except RemoteError as exc:
        _out().print_error("Could not start the remote run", remediation=str(exc))
        raise typer.Exit(1) from exc

    _out().print_success(f"started {run.run_id} on {host}")
    # Printed before any streaming, so a Ctrl-C during --follow still leaves
    # the user with the id they need to reattach.
    typer.echo(f"  tail:  praisonai-train remote tail {host} {run.run_id}")
    typer.echo(f"  stop:  praisonai-train remote stop {host} {run.run_id}")
    if follow:
        runner.tail(run, on_line=lambda line: typer.echo(line))
        typer.echo(f"status: {runner.status(run)}")


@remote_app.command("tail")
def tail(
    host: str = typer.Argument(...),
    run_id: str = typer.Argument(...),
    python: str = typer.Option("python3", "--python"),
    workdir: str = typer.Option("~/.praisonai-train", "--workdir"),
):
    """Reattach to a running job's log."""
    runner = _runner(host, python, workdir)
    run = _run_handle(host, run_id, runner.host.resolve_workdir())
    runner.tail(run, on_line=lambda line: typer.echo(line))
    typer.echo(f"status: {runner.status(run)}")


@remote_app.command("status")
def status(
    host: str = typer.Argument(...),
    run_id: str = typer.Argument(...),
    python: str = typer.Option("python3", "--python"),
    workdir: str = typer.Option("~/.praisonai-train", "--workdir"),
):
    """Whether a run is still going, and how it ended if not."""
    runner = _runner(host, python, workdir)
    run = _run_handle(host, run_id, runner.host.resolve_workdir())
    typer.echo(runner.status(run))


@remote_app.command("fetch")
def fetch(
    host: str = typer.Argument(...),
    run_id: str = typer.Argument(...),
    remote_path: str = typer.Argument(..., help="Path inside the run directory."),
    out: Path = typer.Option(Path("."), "--out", "-o"),
    python: str = typer.Option("python3", "--python"),
    workdir: str = typer.Option("~/.praisonai-train", "--workdir"),
):
    """Bring an artifact back — the adapter, a checkpoint, the log."""
    runner = _runner(host, python, workdir)
    run = _run_handle(host, run_id, runner.host.resolve_workdir())
    from praisonai_train.remote.runner import RemoteError
    try:
        dest = runner.fetch(run, remote_rel=remote_path, dest=out)
    except RemoteError as exc:
        _out().print_error("Could not fetch", remediation=str(exc))
        raise typer.Exit(1) from exc
    _out().print_success(f"fetched to {dest}")


@remote_app.command("stop")
def stop(
    host: str = typer.Argument(...),
    run_id: str = typer.Argument(...),
    python: str = typer.Option("python3", "--python"),
    workdir: str = typer.Option("~/.praisonai-train", "--workdir"),
):
    """Stop a run. Reports whether anything was actually running."""
    runner = _runner(host, python, workdir)
    run = _run_handle(host, run_id, runner.host.resolve_workdir())
    if runner.stop(run):
        _out().print_success(f"stopped {run_id} on {host}")
    else:
        typer.echo(f"{run_id} was not running on {host}")
