"""
Traces command group for PraisonAI CLI.

Provides trace collection management:
- traces enable: Enable trace collection
- traces disable: Disable trace collection
- traces status: Show current status
- traces list: List recent traces
"""

from typing import Optional

import typer

from ..configuration.loader import get_config_loader
from ..output.console import get_output_controller

app = typer.Typer(help="Trace collection management")


@app.command("enable")
def traces_enable(
    endpoint: Optional[str] = typer.Option(
        None,
        "--endpoint",
        "-e",
        help="Trace endpoint URL",
    ),
    sample_rate: float = typer.Option(
        1.0,
        "--sample-rate",
        "-r",
        help="Sample rate (0.0 to 1.0)",
    ),
):
    """Enable trace collection."""
    output = get_output_controller()
    loader = get_config_loader()
    
    loader.set("traces.enabled", True)
    if endpoint:
        loader.set("traces.endpoint", endpoint)
    if sample_rate != 1.0:
        loader.set("traces.sample_rate", sample_rate)
    
    if output.is_json_mode:
        output.print_json({
            "traces_enabled": True,
            "endpoint": endpoint,
            "sample_rate": sample_rate,
        })
    else:
        output.print_success("Trace collection enabled")
        if endpoint:
            output.print(f"  Endpoint: {endpoint}")
        output.print(f"  Sample rate: {sample_rate}")


@app.command("disable")
def traces_disable():
    """Disable trace collection."""
    output = get_output_controller()
    loader = get_config_loader()
    
    loader.set("traces.enabled", False)
    
    if output.is_json_mode:
        output.print_json({"traces_enabled": False})
    else:
        output.print_success("Trace collection disabled")


@app.command("status")
def traces_status():
    """Show trace collection status."""
    output = get_output_controller()
    loader = get_config_loader()
    
    enabled = loader.get("traces.enabled", False)
    endpoint = loader.get("traces.endpoint")
    sample_rate = loader.get("traces.sample_rate", 1.0)
    
    if output.is_json_mode:
        output.print_json({
            "enabled": enabled,
            "endpoint": endpoint,
            "sample_rate": sample_rate,
        })
    else:
        status = "✅ Enabled" if enabled else "❌ Disabled"
        output.print_panel(
            f"Status: {status}\n"
            f"Endpoint: {endpoint or 'Not configured'}\n"
            f"Sample Rate: {sample_rate}",
            title="Trace Collection Status"
        )


@app.command("list")
def traces_list(
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="Maximum number of traces to show",
    ),
):
    """List recent traces."""
    output = get_output_controller()
    
    from ..configuration.paths import get_traces_dir
    
    traces_dir = get_traces_dir()
    
    if not traces_dir.exists():
        if output.is_json_mode:
            output.print_json({"traces": []})
        else:
            output.print_info("No traces found")
        return
    
    traces = []
    for trace_file in sorted(traces_dir.iterdir(), reverse=True)[:limit]:
        if trace_file.is_file() and trace_file.suffix == ".json":
            traces.append({
                "name": trace_file.stem,
                "size": trace_file.stat().st_size,
                "modified": trace_file.stat().st_mtime,
            })
    
    if output.is_json_mode:
        output.print_json({"traces": traces})
    else:
        if not traces:
            output.print_info("No traces found")
            return
        
        headers = ["Name", "Size", "Modified"]
        rows = []
        for t in traces:
            from datetime import datetime
            modified = datetime.fromtimestamp(t["modified"]).strftime("%Y-%m-%d %H:%M")
            rows.append([t["name"], f"{t['size']} bytes", modified])
        
        output.print_table(headers, rows, title="Recent Traces")
