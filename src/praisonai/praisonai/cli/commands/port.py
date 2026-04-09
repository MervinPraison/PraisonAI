"""Port management CLI command for PraisonAI.

Provides commands to manage port usage and resolve port conflicts:
- praisonai port list: List processes using ports
- praisonai port check <port>: Check if a port is in use
- praisonai port kill <port>: Kill process using a port

Examples:
    praisonai port list
    praisonai port check 6379
    praisonai port kill 6379
    praisonai port kill 6379 --force
"""

import re
import subprocess
import sys
from typing import Dict, List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

app = typer.Typer(name="port", help="🔌 Manage port usage and resolve conflicts")
console = Console()


def _get_process_using_port(port: int) -> Optional[Dict]:
    """Get process information for a specific port.
    
    Uses lsof on macOS/Linux and netstat on Windows.
    
    Args:
        port: Port number to check
        
    Returns:
        Dict with process info or None if port is free
    """
    try:
        if sys.platform == "darwin" or sys.platform.startswith("linux"):
            # Use lsof on macOS and Linux
            result = subprocess.run(
                ["lsof", "-i", f":{port}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0 or not result.stdout:
                return None
            
            # Parse lsof output
            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                return None
            
            # First line is header, get first data line
            data_line = lines[1]
            parts = data_line.split()
            
            if len(parts) >= 9:
                return {
                    "name": parts[0],
                    "pid": parts[1],
                    "user": parts[2],
                    "type": parts[4],
                    "protocol": parts[7] if len(parts) > 7 else "TCP",
                    "port": port,
                    "raw": data_line
                }
        
        elif sys.platform == "win32":
            # Use netstat on Windows
            result = subprocess.run(
                ["netstat", "-ano", "|", "findstr", f":{port}"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=5
            )
            
            if result.returncode != 0 or not result.stdout:
                return None
            
            # Parse netstat output
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        # Get process name from PID
                        try:
                            proc_result = subprocess.run(
                                ["tasklist", "/FI", f"PID eq {pid}"],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            name = "unknown"
                            if proc_result.returncode == 0:
                                proc_lines = proc_result.stdout.strip().split("\n")
                                if len(proc_lines) >= 2:
                                    name = proc_lines[1].split()[0]
                            
                            return {
                                "name": name,
                                "pid": pid,
                                "user": "unknown",
                                "type": "IPv4",
                                "protocol": "TCP",
                                "port": port,
                                "raw": line
                            }
                        except Exception:
                            pass
    
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    
    return None


def _get_all_ports() -> List[Dict]:
    """Get list of all processes using network ports.
    
    Returns:
        List of dicts with process information
    """
    processes = []
    
    try:
        if sys.platform == "darwin" or sys.platform.startswith("linux"):
            result = subprocess.run(
                ["lsof", "-i", "-P", "-n"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                # Skip header line
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 9:
                        # Extract port from address
                        addr = parts[8] if len(parts) > 8 else ""
                        port_match = re.search(r":(\d+)", addr)
                        if port_match:
                            port = int(port_match.group(1))
                            processes.append({
                                "name": parts[0],
                                "pid": parts[1],
                                "user": parts[2],
                                "protocol": parts[7] if len(parts) > 7 else "TCP",
                                "port": port,
                                "address": addr
                            })
        
        elif sys.platform == "win32":
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                for line in lines[4:]:  # Skip header lines
                    parts = line.split()
                    if len(parts) >= 5 and ("LISTENING" in line or "ESTABLISHED" in line):
                        local_addr = parts[1]
                        pid = parts[4]
                        port_match = re.search(r":(\d+)", local_addr)
                        if port_match:
                            port = int(port_match.group(1))
                            processes.append({
                                "name": f"PID:{pid}",
                                "pid": pid,
                                "user": "unknown",
                                "protocol": parts[0],
                                "port": port,
                                "address": local_addr
                            })
    
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    
    return processes


def _kill_process(pid: str, force: bool = False) -> bool:
    """Kill a process by PID.
    
    Args:
        pid: Process ID to kill
        force: If True, use SIGKILL (-9) instead of SIGTERM
        
    Returns:
        True if successful, False otherwise
    """
    try:
        if sys.platform == "win32":
            # Windows
            cmd = ["taskkill", "/F", "/PID", str(pid)] if force else ["taskkill", "/PID", str(pid)]
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            return result.returncode == 0
        else:
            # macOS/Linux
            signal = "-9" if force else "-15"
            result = subprocess.run(["kill", signal, str(pid)], capture_output=True, timeout=5)
            return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def _is_port_conflict_error(error_msg: str) -> bool:
    """Check if error message indicates a port conflict.
    
    Args:
        error_msg: Error message to check
        
    Returns:
        True if it's a port conflict error
    """
    port_conflict_patterns = [
        "address already in use",
        "port is already allocated",
        "bind: address already in use",
        "Ports are not available",
        "port.*already.*use",
        "listen tcp.*bind: address already in use"
    ]
    
    error_lower = error_msg.lower()
    for pattern in port_conflict_patterns:
        if pattern.lower() in error_lower:
            return True
    
    return False


def _extract_port_from_error(error_msg: str) -> Optional[int]:
    """Extract port number from error message.
    
    Args:
        error_msg: Error message containing port info
        
    Returns:
        Port number if found, None otherwise
    """
    # Common patterns for port mentions
    patterns = [
        r":(\d+)->",  # Docker style: 127.0.0.1:6379->0.0.0.0:0
        r":(\d+)",    # Generic port format
        r"port\s+(\d+)",  # "port 6379" format
        r"tcp\s+.*:(\d+)",  # TCP with port
    ]
    
    for pattern in patterns:
        match = re.search(pattern, error_msg)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    
    return None


def _show_port_conflict_help(port: int, console: Optional[Console] = None) -> None:
    """Show helpful message when port conflict is detected.
    
    Args:
        port: Port number that caused conflict
        console: Console to print to (creates new if None)
    """
    if console is None:
        console = Console()
    
    # Get process info
    proc = _get_process_using_port(port)
    
    console.print()
    console.print(Panel(
        f"[bold yellow]Port {port} is already in use[/bold yellow]\n\n"
        f"Another process is using port {port}, preventing the service from starting.",
        title="🔌 Port Conflict",
        border_style="red"
    ))
    
    if proc:
        console.print(f"\n[bold]Process using port {port}:[/bold]")
        console.print(f"  Name: {proc['name']}")
        console.print(f"  PID: {proc['pid']}")
        console.print(f"  User: {proc['user']}")
    
    console.print("\n[bold cyan]How to resolve:[/bold cyan]")
    console.print()
    
    # Create a table of options
    table = Table(show_header=False, border_style="dim")
    table.add_column("Option", style="green", no_wrap=True)
    table.add_column("Command", style="cyan")
    table.add_column("Description", style="white")
    
    table.add_row(
        "1. Kill process",
        f"praisonai port kill {port}",
        "Kill the process using this port"
    )
    table.add_row(
        "2. Force kill",
        f"praisonai port kill {port} --force",
        "Force kill if graceful kill fails"
    )
    table.add_row(
        "3. Check details",
        f"praisonai port check {port}",
        "See process details before killing"
    )
    table.add_row(
        "4. List all ports",
        "praisonai port list",
        "See all processes using ports"
    )
    
    console.print(table)
    
    console.print("\n[dim]Or manually:[/dim]")
    if sys.platform == "darwin" or sys.platform.startswith("linux"):
        console.print(f"  [green]lsof -i :{port}[/green]  # See process details")
        console.print("  [green]kill -9 <PID>[/green]  # Kill by PID")
    elif sys.platform == "win32":
        console.print(f"  [green]netstat -ano | findstr :{port}[/green]  # See process details")
        console.print("  [green]taskkill /F /PID <PID>[/green]          # Kill by PID")
    
    console.print()


@app.callback(invoke_without_command=True)
def port_callback(ctx: typer.Context):
    """Manage port usage and resolve conflicts."""
    if ctx.invoked_subcommand is None:
        # Default action: show help
        console.print("[bold]Port Management Commands[/bold]\n")
        console.print("Use [cyan]praisonai port list[/cyan] to see all ports in use")
        console.print("Use [cyan]praisonai port check <port>[/cyan] to check a specific port")
        console.print("Use [cyan]praisonai port kill <port>[/cyan] to free a port\n")
        raise typer.Exit()


@app.command("list")
def port_list(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show all details"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all processes using network ports."""
    processes = _get_all_ports()
    
    if not processes:
        console.print("[yellow]No processes found using network ports.[/yellow]")
        console.print("[dim](May require elevated permissions on some systems)[/dim]")
        raise typer.Exit(0)
    
    if json_output:
        import json
        console.print(json.dumps(processes, indent=2))
        raise typer.Exit(0)
    
    # Create table
    table = Table(title=f"🔌 Processes Using Network Ports ({len(processes)} found)")
    table.add_column("Process", style="cyan", no_wrap=True)
    table.add_column("PID", style="yellow")
    table.add_column("Port", style="green", justify="right")
    table.add_column("Protocol", style="blue")
    table.add_column("User", style="magenta")
    
    if verbose:
        table.add_column("Address", style="dim")
    
    # Sort by port number
    sorted_procs = sorted(processes, key=lambda x: x.get("port", 0))
    
    for proc in sorted_procs:
        row = [
            proc.get("name", "unknown"),
            proc.get("pid", "-"),
            str(proc.get("port", "-")),
            proc.get("protocol", "TCP"),
            proc.get("user", "unknown"),
        ]
        if verbose:
            row.append(proc.get("address", "-"))
        table.add_row(*row)
    
    console.print(table)
    console.print()
    console.print(f"[dim]Tip: Use [cyan]praisonai port kill <port>[/cyan] to free a port[/dim]")


@app.command("check")
def port_check(
    port: int = typer.Argument(..., help="Port number to check"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check if a specific port is in use."""
    proc = _get_process_using_port(port)
    
    if json_output:
        import json
        if proc:
            console.print(json.dumps({"in_use": True, "process": proc}, indent=2))
        else:
            console.print(json.dumps({"in_use": False}, indent=2))
        raise typer.Exit(0)
    
    if proc:
        console.print(f"[red]✗ Port {port} is in use[/red]")
        console.print()
        
        table = Table(title=f"Process Using Port {port}", border_style="red")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        
        table.add_row("Process Name", proc["name"])
        table.add_row("PID", proc["pid"])
        table.add_row("User", proc["user"])
        table.add_row("Protocol", proc["protocol"])
        table.add_row("Type", proc["type"])
        
        console.print(table)
        console.print()
        console.print(f"To free this port: [cyan]praisonai port kill {port}[/cyan]")
        raise typer.Exit(1)
    else:
        console.print(f"[green]✓ Port {port} is available[/green]")
        raise typer.Exit(0)


@app.command("kill")
def port_kill(
    port: int = typer.Argument(..., help="Port number to free"),
    force: bool = typer.Option(False, "--force", "-f", help="Force kill (SIGKILL)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Kill the process using a specific port."""
    proc = _get_process_using_port(port)
    
    if not proc:
        if json_output:
            import json
            console.print(json.dumps({"success": False, "error": f"No process found using port {port}"}, indent=2))
        else:
            console.print(f"[yellow]⚠ No process found using port {port}[/yellow]")
            console.print("[dim]Port may already be free.[/dim]")
        raise typer.Exit(0)
    
    # Show what we're about to kill
    if not json_output:
        console.print(f"\n[bold]Process using port {port}:[/bold]")
        console.print(f"  Name: {proc['name']}")
        console.print(f"  PID: {proc['pid']}")
        console.print(f"  User: {proc['user']}")
        console.print()
    
    # Confirm unless --yes
    if not yes and not json_output:
        if not typer.confirm(f"Kill process {proc['name']} (PID {proc['pid']})?"):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)
    
    # Kill the process
    success = _kill_process(proc["pid"], force=force)
    
    if success:
        if json_output:
            import json
            console.print(json.dumps({
                "success": True,
                "port": port,
                "process": proc["name"],
                "pid": proc["pid"]
            }, indent=2))
        else:
            signal_type = "force killed" if force else "killed"
            console.print(f"[green]✓ Process {proc['name']} (PID {proc['pid']}) {signal_type}[/green]")
            console.print(f"[green]✓ Port {port} is now free[/green]")
        raise typer.Exit(0)
    else:
        if json_output:
            import json
            console.print(json.dumps({
                "success": False,
                "error": f"Failed to kill process {proc['pid']}"
            }, indent=2))
        else:
            console.print(f"[red]✗ Failed to kill process {proc['pid']}[/red]")
            if not force:
                console.print("[yellow]Try: praisonai port kill {port} --force[/yellow]")
        raise typer.Exit(1)


# Export utility functions for use in other modules
__all__ = [
    "app",
    "_is_port_conflict_error",
    "_extract_port_from_error",
    "_show_port_conflict_help",
    "_get_process_using_port",
    "_kill_process",
    "_get_all_ports",
    "port_list",
    "port_check",
    "port_kill",
]
