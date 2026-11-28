"""CLI for remote MCP connectors (alias of `praisonai mcp` + official catalog)."""
from __future__ import annotations
import json
from dataclasses import asdict
from typing import List, Optional
import typer
from praisonai_mcp.cli.commands.mcp import mcp_add, mcp_list, mcp_remove, mcp_test
from praisonai_mcp.connect.connectors_catalog import CONNECTOR_CATALOG, get_connector, list_connectors

app = typer.Typer(
    help="Connect remote MCP services like GitHub, Linear, Notion (alias of 'praisonai mcp' + catalog; unlike 'praisonai connect' which registers PraisonAI in editors)"
)

@app.command("catalog")
def connectors_catalog(json_output: bool = typer.Option(False, "--json", help="Output JSON")):
    """List built-in official remote MCP connectors."""
    entries = list_connectors()
    if json_output:
        typer.echo(json.dumps({"connectors": [asdict(e) for e in entries]}, indent=2))
        return
    for e in entries:
        typer.echo(f"{e.id:<14} {e.label:<14} [{'oauth' if e.oauth else 'no-auth':<7}] {e.url}")

@app.command("list")
def connectors_list(json_output: bool = typer.Option(False, "--json", help="Output JSON")):
    """List configured connectors (MCP servers)."""
    mcp_list(json_output=json_output)

@app.command("add")
def connectors_add(
    name: str = typer.Argument(..., help="Catalog connector name or custom server name"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Custom remote MCP server URL"),
    header: Optional[List[str]] = typer.Option(None, "--header", "-H", help="HTTP header (KEY=VALUE, repeatable)"),
    oauth: bool = typer.Option(False, "--oauth", help="Enable OAuth 2.1 authentication"),
    allow: Optional[List[str]] = typer.Option(None, "--allow", help="Allowed tool names (comma-separated or repeatable)"),
):
    """Add a remote MCP connector from the official catalog or by custom --url."""
    resolved_url, resolved_oauth = url, oauth
    if not resolved_url:
        entry = get_connector(name)
        if entry is None:
            typer.echo(f"Unknown connector '{name}'. Available: {', '.join(CONNECTOR_CATALOG)}. Or pass --url <URL>.", err=True)
            raise typer.Exit(1)
        resolved_url, resolved_oauth = entry.url, oauth or entry.oauth
    mcp_add(name=name, command=None, args=None, env=None, url=resolved_url, header=header, oauth=resolved_oauth, allow=allow)

@app.command("remove")
def connectors_remove(name: str = typer.Argument(..., help="Connector name"), confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation")):
    """Remove a configured connector."""
    mcp_remove(name=name, confirm=confirm)

@app.command("test")
def connectors_test(name: str = typer.Argument(..., help="Connector name"), timeout: float = typer.Option(10.0, "--timeout", "-t", help="Timeout in seconds")):
    """Test a configured connector using a real MCP handshake."""
    mcp_test(name=name, timeout=timeout)
