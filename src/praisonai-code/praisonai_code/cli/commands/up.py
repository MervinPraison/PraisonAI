"""PraisonAI Up — Unified startup command.

Starts Langfuse + Langflow + observability in one command for
the complete PraisonAI × Langfuse × Langflow experience.
"""

import os
import signal
import subprocess
import time
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(name="up", help="Start unified PraisonAI stack (Langfuse + Langflow + tracing)")


class ServiceManager:
    """Manages multiple services with graceful shutdown."""
    
    def __init__(self):
        self.services: List[subprocess.Popen] = []
        self.console = Console()
    
    def add_service(self, cmd: List[str], name: str, env: Optional[dict] = None) -> subprocess.Popen:
        """Start a service and add to managed list."""
        self.console.print(f"[cyan]Starting {name}...[/cyan]")
        
        try:
            proc = subprocess.Popen(
                cmd,
                env=env or os.environ.copy(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.services.append(proc)
            self.console.print(f"[green]✅ {name} started (PID: {proc.pid})[/green]")
            return proc
            
        except Exception as e:
            self.console.print(f"[red]❌ Failed to start {name}: {e}[/red]")
            raise typer.Abort()
    
    def wait_for_service(self, url: str, service_name: str, timeout: int = 60) -> bool:
        """Wait for service to become healthy."""
        try:
            import requests
        except ImportError:
            self.console.print(f"[yellow]⚠️ Cannot health-check {service_name} (requests not installed)[/yellow]")
            return True
        
        self.console.print(f"[cyan]Waiting for {service_name} at {url}...[/cyan]")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{url}/api/v1/health", timeout=5)
                if response.status_code == 200:
                    self.console.print(f"[green]✅ {service_name} is ready![/green]")
                    return True
            except requests.RequestException:
                pass
            
            time.sleep(2)
        
        self.console.print(f"[yellow]⚠️ {service_name} health check timed out[/yellow]")
        return False
    
    def shutdown_all(self):
        """Gracefully shutdown all services."""
        if not self.services:
            return
        
        self.console.print("\n[yellow]Shutting down services...[/yellow]")
        
        # Send SIGTERM to all processes
        for proc in self.services:
            if proc.poll() is None:  # Process still running
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
        
        # Wait for graceful shutdown
        time.sleep(3)
        
        # Force kill any remaining processes
        for proc in self.services:
            if proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    pass
        
        self.console.print("[green]✅ All services stopped[/green]")


@app.callback(invoke_without_command=True)
def up_start(
    ctx: typer.Context,
    # Langfuse options
    langfuse_port: int = typer.Option(3000, "--langfuse-port", help="Langfuse port"),
    no_langfuse: bool = typer.Option(False, "--no-langfuse", help="Skip starting Langfuse"),
    
    # Langflow options  
    langflow_port: int = typer.Option(7860, "--langflow-port", help="Langflow port"),
    no_langflow: bool = typer.Option(False, "--no-langflow", help="Skip starting Langflow"),
    
    # Observability options
    observe: str = typer.Option("langfuse", "--observe", help="Enable observability (langfuse)"),
    
    # General options
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open browser"),
    wait_timeout: int = typer.Option(60, "--wait", help="Seconds to wait for services"),
):
    """Start unified PraisonAI stack.
    
    Launches Langfuse (observability) + Langflow (visual builder) with
    automatic observability wiring. The complete PraisonAI experience.
    
    Examples:
        praisonai up
        praisonai up --no-langfuse  # Langflow only
        praisonai up --no-langflow  # Langfuse only
        praisonai up --host 0.0.0.0 --langfuse-port 3001
    """
    if ctx.invoked_subcommand is not None:
        return
    
    console = Console()
    manager = ServiceManager()
    
    # Validate options
    if no_langfuse and no_langflow:
        console.print("[red]Error: Cannot skip both Langfuse and Langflow[/red]")
        raise typer.Abort()
    
    # Show startup banner
    console.print()
    console.print(Panel.fit(
        "[bold green]🚀 PraisonAI Stack Starting[/bold green]\n\n"
        f"[cyan]Langfuse:[/cyan] {'✅ Enabled' if not no_langfuse else '❌ Disabled'} "
        f"(port {langfuse_port})\n"
        f"[cyan]Langflow:[/cyan] {'✅ Enabled' if not no_langflow else '❌ Disabled'} "
        f"(port {langflow_port})\n"
        f"[cyan]Observability:[/cyan] {observe}",
        title="PraisonAI Up",
        border_style="green"
    ))
    console.print()
    
    try:
        import sys
        
        # Setup environment for observability
        env = os.environ.copy()
        if observe == "langfuse" and not no_langfuse:
            # Configure Langfuse environment
            env["LANGFUSE_HOST"] = f"http://{host}:{langfuse_port}"
            env["PRAISONAI_OBSERVE"] = "langfuse"
        
        # Suppress macOS warnings
        if sys.platform == "darwin":
            env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
        
        services_started = []
        
        # Start Langfuse
        if not no_langfuse:
            try:
                # Check if praisonai langfuse command exists
                langfuse_cmd = [
                    sys.executable, "-m", "praisonai.cli.main", "langfuse",
                    "--port", str(langfuse_port),
                    "--host", host,
                ]
                
                langfuse_proc = manager.add_service(langfuse_cmd, "Langfuse", env)
                services_started.append(("Langfuse", f"http://{host}:{langfuse_port}"))
                
                # Wait for Langfuse to be ready
                if wait_timeout > 0:
                    manager.wait_for_service(
                        f"http://{host}:{langfuse_port}", 
                        "Langfuse", 
                        timeout=wait_timeout
                    )
                    
            except Exception as e:
                console.print(f"[red]Failed to start Langfuse: {e}[/red]")
                console.print("[yellow]Try: pip install 'praisonai[langfuse]'[/yellow]")
                if not no_langflow:
                    console.print("[cyan]Continuing with Langflow only...[/cyan]")
        
        # Start Langflow
        if not no_langflow:
            try:
                # Get path to praisonai flow command
                langflow_cmd = [
                    sys.executable, "-m", "praisonai.cli.main", "flow",
                    "--port", str(langflow_port),
                    "--host", host,
                    "--no-open",  # We'll handle browser opening
                ]
                
                langflow_proc = manager.add_service(langflow_cmd, "Langflow", env)
                services_started.append(("Langflow", f"http://{host}:{langflow_port}"))
                
                # Wait for Langflow to be ready
                if wait_timeout > 0:
                    manager.wait_for_service(
                        f"http://{host}:{langflow_port}", 
                        "Langflow", 
                        timeout=wait_timeout
                    )
                    
            except Exception as e:
                console.print(f"[red]Failed to start Langflow: {e}[/red]")
                console.print("[yellow]Try: pip install 'praisonai[flow]'[/yellow]")
        
        if not services_started:
            console.print("[red]No services started successfully[/red]")
            raise typer.Abort()
        
        # Show service summary
        console.print()
        table = Table(title="🎉 Services Ready")
        table.add_column("Service", style="cyan")
        table.add_column("URL", style="green")
        table.add_column("Status", style="bold")
        
        for service_name, service_url in services_started:
            table.add_row(service_name, service_url, "✅ Running")
        
        console.print(table)
        
        # Show usage instructions
        console.print()
        console.print(Panel(
            "[bold]Quick Start:[/bold]\n\n"
            "1. Open Langflow in your browser to build visual workflows\n"
            "2. Use PraisonAI Agent/AgentTeam components from the sidebar\n"  
            "3. Run workflows with: [cyan]praisonai run workflow.yaml --observe langfuse[/cyan]\n"
            "4. View traces in Langfuse dashboard\n\n"
            "[dim]Press Ctrl+C to stop all services[/dim]",
            title="Next Steps",
            border_style="blue"
        ))
        
        # Open browser if requested
        if not no_open and not no_langflow:
            try:
                import webbrowser
                webbrowser.open(f"http://{host}:{langflow_port}")
                console.print("[dim]Opening Langflow in browser...[/dim]")
            except Exception:
                pass
        
        # Setup signal handler for graceful shutdown
        def signal_handler(signum, frame):
            raise KeyboardInterrupt()  # Let the try/except/finally handle cleanup
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Keep running until interrupted
        try:
            while True:
                time.sleep(1)
                # Check if any service died
                for proc in manager.services[:]:
                    if proc.poll() is not None:
                        console.print(f"[red]Service died (exit code: {proc.returncode})[/red]")
                        manager.services.remove(proc)
                
                # If all services died, exit
                if not manager.services:
                    console.print("[yellow]All services stopped[/yellow]")
                    break
                    
        except KeyboardInterrupt:
            pass
        finally:
            manager.shutdown_all()
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        manager.shutdown_all()
        raise typer.Abort()


@app.command("status")
def up_status(
    langfuse_url: str = typer.Option("http://localhost:3000", "--langfuse-url", help="Langfuse URL"),
    langflow_url: str = typer.Option("http://localhost:7860", "--langflow-url", help="Langflow URL"),
):
    """Check status of PraisonAI services."""
    console = Console()
    
    try:
        import requests
    except ImportError:
        console.print("[red]requests package required for status checks[/red]")
        raise typer.Abort()
    
    table = Table(title="Service Status")
    table.add_column("Service", style="cyan")
    table.add_column("URL", style="blue") 
    table.add_column("Status", style="bold")
    table.add_column("Response Time", style="dim")
    
    services = [
        ("Langfuse", langfuse_url),
        ("Langflow", langflow_url),
    ]
    
    for service_name, service_url in services:
        try:
            start_time = time.time()
            response = requests.get(f"{service_url}/health", timeout=5)
            response_time = f"{(time.time() - start_time)*1000:.0f}ms"
            
            if response.status_code == 200:
                status = "✅ Healthy"
                status_style = "green"
            else:
                status = f"⚠️ Error {response.status_code}"
                status_style = "yellow"
                
        except requests.RequestException as e:
            status = "❌ Down"
            status_style = "red"
            response_time = "N/A"
        
        table.add_row(service_name, service_url, status, response_time)
    
    console.print(table)


@app.command("logs")
def up_logs(
    service: str = typer.Option("all", "--service", help="Service to show logs for (all, langfuse, langflow)"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show"),
):
    """Show logs from PraisonAI services."""
    console = Console()
    console.print("[yellow]Log viewing not implemented yet[/yellow]")
    console.print("[dim]Use docker logs or check process output directly[/dim]")