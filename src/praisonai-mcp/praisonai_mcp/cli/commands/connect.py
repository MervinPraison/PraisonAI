"""``praisonai connect``: put PraisonAI in your editor or agent, in one command.

    praisonai connect                    # which clients are installed / connected / last active
    praisonai connect cursor             # write Cursor's config (diff, backup), then verify
    praisonai connect --all              # every installed client
    praisonai connect codex --tools 'ask_*' --agents agents.yaml
    praisonai connect cursor --print     # deep link, command and JSON; writes nothing
    praisonai connect --remove           # undo everywhere it was added
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import typer

from praisonai_mcp.connect import catalog as cat
from praisonai_mcp.connect import config_io, probe

app = typer.Typer(help="Connect editors and agents (Cursor, VS Code, Claude, Codex…) to PraisonAI over MCP")

#: Where macOS apps are looked for (a test points this at a temp folder).
APPS_DIRS = (Path("/Applications"), Path.home() / "Applications")


def _console(stderr: bool = False):
    from rich.console import Console

    return Console(highlight=False, stderr=stderr)


def installed(client: cat.Client, home: Path) -> bool:
    if any((d / app_name).exists() for d in APPS_DIRS for app_name in client.apps):
        return True
    if any(shutil.which(b) for b in client.bins):
        return True
    return any((home / d).is_dir() for d in client.dirs)


def _ago(stamp: Optional[float]) -> str:
    if not stamp:
        return ""
    d = max(0, time.time() - stamp)
    for unit, size in (("d", 86400), ("h", 3600), ("min", 60)):
        if d >= size:
            return f"{int(d // size)} {unit} ago"
    return "just now"


def status_rows(home: Path, name: str = cat.SERVER_NAME) -> List[Dict[str, Any]]:
    """One row per client: installed / connected, last active, warnings."""
    seen: Dict[str, Dict[str, Any]] = {}
    for row in probe.connections():
        cid = cat.client_for(str(row.get("name", "")))
        if cid and cid not in seen:
            seen[cid] = row
    rows = []
    for c in cat.CLIENTS:
        if c.path is None:
            continue
        stored = config_io.read_entry(c, home, name)
        state = "connected" if stored is not None else ("installed" if installed(c, home) else "not installed")
        last = seen.get(c.id, {})
        rows.append({
            "id": c.id, "label": c.label, "group": c.group, "status": state,
            "config_path": str(cat.config_path(c, home)),
            "last_active": last.get("last_active"),
            "plaintext_secrets": config_io.plaintext_secrets(stored),
        })
    return rows


def _show_status(home: Path, as_json: bool) -> None:
    rows = status_rows(home)
    if as_json:
        typer.echo(json.dumps({"clients": rows, "connections": probe.connections()}, indent=2))
        return
    from rich.table import Table

    con = _console()
    table = Table(title="MCP clients on this machine", title_justify="left")
    for col in ("Client", "Status", "Last active", "Config"):
        table.add_column(col)
    colour = {"connected": "green", "installed": "yellow", "not installed": "dim"}
    for r in rows:
        status = f"[{colour[r['status']]}]{r['status']}[/]"
        if r["plaintext_secrets"]:
            status += f"\n[red]plain-text secret: {', '.join(r['plaintext_secrets'])}[/]"
        table.add_row(f"{r['label']} [dim]({r['id']})[/]", status, _ago(r["last_active"]), f"[dim]{r['config_path']}[/]")
    con.print(table)
    ready = [r["id"] for r in rows if r["status"] == "installed"]
    if ready:
        con.print(f"Connect one: [bold]praisonai connect {ready[0]}[/]   all installed: [bold]praisonai connect --all[/]")


def _print_client(client: cat.Client, spec: cat.ServerSpec, home: Path) -> Dict[str, Any]:
    try:
        return {"id": client.id, "label": client.label, "deeplink": cat.deeplink(client, spec),
                "command": cat.command(client, spec), "snippet": cat.snippet(client, spec),
                "config_path": str(cat.config_path(client, home) or ""), "note": client.note}
    except ValueError as exc:
        return {"id": client.id, "label": client.label, "error": str(exc)}


def _targets(clients: List[str], all_: bool, home: Path, connected_only: bool = False) -> List[cat.Client]:
    if clients:
        try:
            return [cat.get_client(c) for c in clients]
        except KeyError as exc:
            raise typer.BadParameter(str(exc.args[0])) from None
    if connected_only:
        return [c for c in cat.CLIENTS if c.path and config_io.read_entry(c, home, cat.SERVER_NAME) is not None]
    if all_:
        return [c for c in cat.CLIENTS if c.path and installed(c, home)]
    return []


@app.command("connect")
def connect(
    clients: List[str] = typer.Argument(None, help=f"Client ids: {', '.join(cat.BY_ID)}"),
    all_: bool = typer.Option(False, "--all", help="Every installed client"),
    remove: bool = typer.Option(False, "--remove", help="Remove the praisonai entry (all connected clients when none named)"),
    print_only: bool = typer.Option(False, "--print", help="Show the deep link, command and config; write nothing"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the diff; write nothing"),
    tools: Optional[str] = typer.Option(None, "--tools", help="Only these tools (comma-separated names or globs)"),
    agents: Optional[str] = typer.Option(None, "--agents", help="Expose the agents in this agents.yaml as tools"),
    url: Optional[str] = typer.Option(None, "--url", help="Point clients at a running HTTP MCP server instead"),
    env: Optional[List[str]] = typer.Option(None, "--env", help="Env var NAME to reference (repeatable; never its value)"),
    verify: bool = typer.Option(True, "--verify/--no-verify", help="Handshake with the server after writing"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Connect editors and agents to PraisonAI's MCP server."""
    home = Path(os.environ.get("HOME") or Path.home())
    scope = [t.strip() for t in (tools or "").split(",") if t.strip()]
    if agents and not Path(agents).expanduser().is_file():
        raise typer.BadParameter(f"{agents} not found", param_hint="--agents")
    if url and (scope or agents):
        raise typer.BadParameter("--tools/--agents scope the local server; scope a remote one where it is served")
    spec = (cat.ServerSpec(url=url, env=tuple(env or ())) if url
            else cat.local_spec(scope, agents, env))

    if url and urlparse(url).hostname in ("localhost", "127.0.0.1", "::1"):
        cloud = [c.label for c in (_targets(clients, all_, home) or cat.CLIENTS) if c.cloud]
        if cloud:
            _console(stderr=True).print(f"[yellow]{', '.join(cloud)} connect from their vendor's cloud and cannot "
                                        "reach localhost: give them a public https URL (a tunnel works).[/]")

    if print_only:
        targets = _targets(clients, all_, home) or [c for c in cat.CLIENTS]
        out = [_print_client(c, spec, home) for c in targets]
        if as_json:
            typer.echo(json.dumps(out, indent=2))
            return
        con = _console()
        for item in out:
            con.rule(item["label"])
            if item.get("error"):
                con.print(f"[yellow]{item['error']}[/]")
                continue
            if item["deeplink"]:
                con.print("[bold]One-click link[/]", item["deeplink"], soft_wrap=True)
            if item["command"]:
                con.print("[bold]Command[/]", item["command"], soft_wrap=True)
            if item["config_path"]:
                con.print(f"[bold]Or add to[/] {item['config_path']}")
            con.print(item["snippet"], markup=False)
        return

    targets = _targets(clients, all_, home, connected_only=remove and not clients)
    if not targets:
        if remove:
            typer.echo("Nothing to remove: no client has a praisonai entry.")
            return
        if all_:
            typer.echo("No MCP client found on this machine. See `praisonai connect --print`.")
            raise typer.Exit(1)
        _show_status(home, as_json)
        return

    con = _console(stderr=as_json)
    results: List[Dict[str, Any]] = []
    for client in targets:
        try:
            plan = config_io.plan_remove(client, home, spec.name) if remove else config_io.plan_write(client, spec, home)
        except (config_io.ConfigError, ValueError) as exc:
            results.append({"id": client.id, "ok": False, "error": str(exc)})
            con.print(f"[red]✗ {client.label}[/]: {exc}")
            continue
        if plan is None or not plan.changed:
            results.append({"id": client.id, "ok": True, "changed": False})
            con.print(f"[green]✓ {client.label}[/]: {'not connected' if remove else 'already up to date'}")
            continue
        if not as_json:
            con.print(plan.diff, markup=False, highlight=False, soft_wrap=True)
        if dry_run:
            results.append({"id": client.id, "ok": True, "changed": True, "dry_run": True, "diff": plan.diff})
            continue
        backup = config_io.apply(plan)
        results.append({"id": client.id, "ok": True, "changed": True, "path": str(plan.path),
                        "backup": str(backup) if backup else None})
        con.print(f"[green]✓ {client.label}[/]: {'removed from' if remove else 'wrote'} {plan.path}"
                  + (f" [dim](backup {backup.name})[/]" if backup else ""))
        if client.note and not remove:
            con.print(f"  [dim]{client.note}[/]")
        if not client.env_ref and client.shape != "codex" and spec.env and not remove:
            con.print(f"  [dim]{client.label} cannot reference env vars: start it from a shell that has "
                      f"{', '.join(spec.env)} set. Nothing secret was written.[/]")

    probe_result = None
    if verify and not remove and not dry_run and any(r.get("ok") for r in results):
        probe_result = probe.verify(spec)
        if probe_result.ok:
            con.print(f"[bold green]{probe_result.tools} tools ready[/] from {probe_result.server or spec.name}.")
            for client in targets:
                if client.max_tools and probe_result.tools > client.max_tools:
                    con.print(f"[yellow]{client.label} uses at most {client.max_tools} tools:[/] "
                              f"scope with --tools (e.g. --tools 'ask_*').")
        else:
            con.print(f"[red]The server did not answer the MCP handshake:[/] {probe_result.error}")
    if as_json:
        typer.echo(json.dumps({"results": results, "verify": probe_result.__dict__ if probe_result else None}, indent=2))
    if any(not r.get("ok") for r in results) or (probe_result and not probe_result.ok):
        raise typer.Exit(1)
