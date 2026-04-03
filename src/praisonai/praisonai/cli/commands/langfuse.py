"""PraisonAI Langfuse — Observability platform for LLM apps.

Provides `praisonai langfuse` CLI commands to manage local (Docker) and remote
Langfuse instances for observability and evaluation of agent workflows.
"""

import os
import json
import subprocess
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="langfuse", help="🔍 Langfuse observability platform")


def _format_publishers(publishers):
    """Format Publishers field for display in status table."""
    if isinstance(publishers, list) and publishers:
        # Publishers is array of port mapping objects
        ports = []
        for pub in publishers:
            if isinstance(pub, dict):
                url = pub.get("URL", "")
                target_port = pub.get("TargetPort", "")
                published_port = pub.get("PublishedPort", "")
                protocol = pub.get("Protocol", "tcp")
                if published_port and target_port:
                    ports.append(f"{url}:{published_port}->{target_port}/{protocol}")
        return ", ".join(ports) if ports else ""
    elif isinstance(publishers, str):
        return publishers  # Fallback for string format
    else:
        return ""


@app.callback(invoke_without_command=True)
def langfuse_start(
    ctx: typer.Context,
    port: int = typer.Option(3000, "--port", "-p", help="Port to listen on"),
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="Host to bind to"),
    detach: bool = typer.Option(True, "--detach/--no-detach", help="Run in background"),
    data_dir: str = typer.Option(
        None, "--data-dir", help="Data directory (default: ~/.praisonai/langfuse)"
    ),
):
    """Start local Langfuse server (Docker).
    
    Clones Langfuse repo and starts the full Docker Compose stack
    with web UI, worker, PostgreSQL, ClickHouse, Redis, and MinIO.
    
    Examples:
        praisonai langfuse
        praisonai langfuse --port 8080
        praisonai langfuse --no-detach
    """
    if ctx.invoked_subcommand is not None:
        return
    
    console = Console()
    
    # Check Docker availability
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        subprocess.run(["docker", "compose", "version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("[red]Docker or Docker Compose is not installed or not running.[/red]")
        console.print("[yellow]Please install Docker and ensure the daemon is running.[/yellow]")
        raise typer.Abort()
    
    # Set up data directory
    if data_dir is None:
        data_dir = os.path.expanduser("~/.praisonai/langfuse")
    data_path = Path(data_dir)
    repo_path = data_path / "langfuse"
    
    console.print(f"[blue]📁 Data directory: {data_path}[/blue]")
    
    # Clone Langfuse repo if not present
    if not repo_path.exists():
        console.print("[yellow]📥 Cloning Langfuse repository...[/yellow]")
        data_path.mkdir(parents=True, exist_ok=True)
        
        try:
            subprocess.run([
                "git", "clone", 
                "https://github.com/langfuse/langfuse.git",
                str(repo_path)
            ], check=True, cwd=data_path)
            console.print("[green]✅ Repository cloned successfully[/green]")
        except subprocess.CalledProcessError:
            console.print("[red]❌ Failed to clone Langfuse repository[/red]")
            raise typer.Abort()
    else:
        console.print("[green]✅ Langfuse repository already exists[/green]")
    
    # Check if containers are already running
    try:
        result = subprocess.run([
            "docker", "compose", "ps", "--format", "table"
        ], cwd=repo_path, capture_output=True, text=True)
        
        if "langfuse-web" in result.stdout and "Up" in result.stdout:
            console.print("[yellow]⚠️  Langfuse is already running[/yellow]")
            console.print(f"[blue]🌐 Access UI: http://{host}:{port}[/blue]")
            return
    except subprocess.CalledProcessError:
        pass
    
    # Update docker-compose.yml port if different from default
    if port != 3000:
        compose_file = repo_path / "docker-compose.yml"
        if compose_file.exists():
            content = compose_file.read_text()
            content = content.replace("3000:3000", f"{port}:3000")
            compose_file.write_text(content)
    
    # Start Docker Compose
    console.print(f"[blue]🚀 Starting Langfuse on {host}:{port}[/blue]")
    console.print("[dim]This may take a few minutes on first run (downloading images)...[/dim]")
    
    cmd = ["docker", "compose", "up"]
    if detach:
        cmd.append("-d")
    
    try:
        if detach:
            subprocess.run(cmd, cwd=repo_path, check=True)
            console.print("[green]✅ Langfuse started successfully[/green]")
            
            # Wait for health check
            console.print("[yellow]⏳ Waiting for services to be ready...[/yellow]")
            try:
                import requests as requests_lib
            except ImportError:
                requests_lib = None
            max_wait = 180  # 3 minutes
            for i in range(max_wait):
                try:
                    if requests_lib is None:
                        break
                    response = requests_lib.get(f"http://{host}:{port}", timeout=5)
                    if response.status_code < 500:
                        break
                except Exception:
                    pass
                time.sleep(1)
                if i % 10 == 0:
                    console.print(f"[dim]Still waiting... ({i}s/{max_wait}s)[/dim]")
            else:
                console.print("[yellow]⚠️  Service may still be starting up[/yellow]")
            
            console.print()
            console.print("[bold green]🎉 Langfuse is ready![/bold green]")
            console.print(f"[blue]🌐 Web UI: http://{host}:{port}[/blue]")
            console.print("[dim]Default login: admin@langfuse.com / admin[/dim]")
            console.print()
            console.print("Next steps:")
            console.print("1. Open the web UI and create your first project")
            console.print("2. Get API keys from Settings > API Keys")
            console.print(f"3. Run: praisonai langfuse config --public-key pk-... --secret-key sk-...")
            console.print("4. Test: praisonai langfuse test")
            
        else:
            subprocess.run(cmd, cwd=repo_path)
            
    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌ Failed to start Langfuse: {e}[/red]")
        console.print("[yellow]Check Docker logs with: docker compose logs[/yellow]")
        raise typer.Abort()
    except KeyboardInterrupt:
        console.print("\n[yellow]⏹️  Stopping Langfuse...[/yellow]")


@app.command("stop")
def langfuse_stop(
    data_dir: str = typer.Option(
        None, "--data-dir", help="Data directory (default: ~/.praisonai/langfuse)"
    ),
):
    """Stop local Langfuse server."""
    console = Console()
    
    # Set up data directory
    if data_dir is None:
        data_dir = os.path.expanduser("~/.praisonai/langfuse")
    repo_path = Path(data_dir) / "langfuse"
    
    if not repo_path.exists():
        console.print("[yellow]⚠️  Langfuse repository not found[/yellow]")
        return
    
    console.print("[yellow]⏹️  Stopping Langfuse...[/yellow]")
    
    try:
        subprocess.run(["docker", "compose", "down"], cwd=repo_path, check=True)
        console.print("[green]✅ Langfuse stopped successfully[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌ Failed to stop Langfuse: {e}[/red]")
        raise typer.Abort()


@app.command("status")
def langfuse_status(
    data_dir: str = typer.Option(
        None, "--data-dir", help="Data directory (default: ~/.praisonai/langfuse)"
    ),
):
    """Check Langfuse server status."""
    console = Console()
    
    # Set up data directory
    if data_dir is None:
        data_dir = os.path.expanduser("~/.praisonai/langfuse")
    repo_path = Path(data_dir) / "langfuse"
    
    if not repo_path.exists():
        console.print("[yellow]⚠️  Langfuse repository not found[/yellow]")
        console.print("Run 'praisonai langfuse' to set up Langfuse")
        return
    
    try:
        import requests as requests_lib
    except ImportError:
        requests_lib = None

    # Check Docker containers
    try:
        result = subprocess.run([
            "docker", "compose", "ps", "--format", "json"
        ], cwd=repo_path, capture_output=True, text=True, check=True)
        
        if not result.stdout.strip():
            console.print("[yellow]📊 No Langfuse containers running[/yellow]")
            return
        
        # Parse JSON output
        containers = []
        for line in result.stdout.strip().split('\n'):
            if line:
                containers.append(json.loads(line))
        
        # Create status table
        table = Table(title="Langfuse Services")
        table.add_column("Service", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Ports", style="blue")
        table.add_column("Health", style="yellow")
        
        for container in containers:
            status_color = "green" if container.get("State") == "running" else "red"
            health = container.get("Health", "unknown")
            
            table.add_row(
                container.get("Service", "unknown"),
                f"[{status_color}]{container.get('State', 'unknown')}[/{status_color}]",
                _format_publishers(container.get("Publishers", [])),
                health
            )
        
        console.print(table)
        
        # Test API availability
        web_running = any(
            c.get("Service") == "langfuse-web" and c.get("State") == "running"
            for c in containers
        )
        
        if web_running:
            # Extract port from web service
            web_container = next(
                c for c in containers 
                if c.get("Service") == "langfuse-web"
            )
            # Extract published port from Publishers array
            publishers = web_container.get("Publishers", [])
            port = "3000"
            if isinstance(publishers, list) and publishers:
                # Publishers is array of {"URL": "0.0.0.0", "TargetPort": 80, "PublishedPort": 8080, "Protocol": "tcp"}
                for pub in publishers:
                    if isinstance(pub, dict) and pub.get("TargetPort") == 3000:
                        port = str(pub.get("PublishedPort", 3000))
                        break
            elif isinstance(publishers, str) and ":" in publishers:
                # Fallback for older format or edge cases
                import re
                match = re.search(r":(\d+)->", publishers)
                port = match.group(1) if match else "3000"
            
            try:
                if requests_lib is not None:
                    response = requests_lib.get(f"http://127.0.0.1:{port}", timeout=5)
                    if response.status_code < 500:
                        console.print(f"[green]🌐 Web UI available: http://127.0.0.1:{port}[/green]")
                    else:
                        console.print(f"[yellow]🌐 Web UI starting: http://127.0.0.1:{port}[/yellow]")
                else:
                    console.print(f"[blue]🌐 Web UI: http://127.0.0.1:{port}[/blue]")
            except Exception:
                console.print(f"[red]🌐 Web UI not responding: http://127.0.0.1:{port}[/red]")
        
    except subprocess.CalledProcessError:
        console.print("[red]❌ Failed to check container status[/red]")
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")


@app.command("config")
def langfuse_config(
    public_key: str = typer.Option(None, "--public-key", "-pk", help="Langfuse public key"),
    secret_key: str = typer.Option(None, "--secret-key", "-sk", help="Langfuse secret key"),
    host: str = typer.Option(None, "--host", help="Langfuse host URL"),
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
):
    """Configure Langfuse connection credentials."""
    console = Console()
    
    config_dir = Path.home() / ".praisonai"
    config_file = config_dir / "langfuse.env"
    
    if show:
        # Show current configuration
        if config_file.exists():
            console.print(f"[blue]📄 Configuration file: {config_file}[/blue]")
            content = config_file.read_text()
            
            table = Table(title="Langfuse Configuration")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")
            
            for line in content.strip().split('\n'):
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    # Mask secret key for security
                    if "SECRET" in key:
                        value = value[:8] + "..." if len(value) > 8 else "***"
                    table.add_row(key, value)
            
            console.print(table)
            
            # Also show env vars
            env_vars = []
            for var in ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST", "LANGFUSE_BASE_URL"]:
                value = os.environ.get(var)
                if value:
                    if "SECRET" in var:
                        value = value[:8] + "..." if len(value) > 8 else "***"
                    env_vars.append((var, value))
            
            if env_vars:
                console.print("\n[blue]🌍 Environment Variables:[/blue]")
                for var, value in env_vars:
                    console.print(f"  {var}={value}")
        else:
            console.print("[yellow]⚠️  No configuration file found[/yellow]")
        
        return
    
    # Set configuration
    if not any([public_key, secret_key, host]):
        console.print("[red]❌ At least one option must be provided[/red]")
        console.print("Use --show to view current configuration")
        raise typer.Abort()
    
    # Read existing config
    config_data = {}
    if config_file.exists():
        content = config_file.read_text()
        for line in content.strip().split('\n'):
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                config_data[key] = value
    
    # Update with new values
    if public_key:
        config_data["LANGFUSE_PUBLIC_KEY"] = public_key
    if secret_key:
        config_data["LANGFUSE_SECRET_KEY"] = secret_key
    if host:
        config_data["LANGFUSE_HOST"] = host
    
    # Write config
    config_dir.mkdir(exist_ok=True)
    
    content_lines = [
        "# Langfuse Configuration",
        "# Generated by PraisonAI CLI",
        ""
    ]
    for key, value in config_data.items():
        content_lines.append(f"{key}={value}")
    
    config_file.write_text('\n'.join(content_lines) + '\n')
    
    console.print(f"[green]✅ Configuration saved to {config_file}[/green]")
    console.print("\n[blue]💡 To use this configuration, either:[/blue]")
    console.print(f"  1. Source it: source {config_file}")
    console.print("  2. Export variables manually")
    console.print("  3. Set them in your shell profile")


@app.command("connect")
def langfuse_connect(
    public_key: str = typer.Option(..., "--public-key", "-pk", help="Langfuse public key"),
    secret_key: str = typer.Option(..., "--secret-key", "-sk", help="Langfuse secret key"),
    host: str = typer.Option("https://cloud.langfuse.com", "--host", help="Langfuse host URL"),
):
    """Configure connection to remote Langfuse instance."""
    return langfuse_config(public_key=public_key, secret_key=secret_key, host=host)


@app.command("test")
def langfuse_test():
    """Emit a test trace to verify Langfuse connectivity."""
    console = Console()
    
    try:
        from praisonai.observability.langfuse import LangfuseSink, LangfuseSinkConfig
        from praisonaiagents.trace.protocol import ActionEvent, ActionEventType, TraceEmitter
        import time
    except ImportError as e:
        console.print(f"[red]❌ Import error: {e}[/red]")
        console.print("[yellow]Install with: pip install praisonai[langfuse][/yellow]")
        raise typer.Abort()
    
    # Load configuration from env vars and ~/.praisonai/langfuse.env if present
    config_file = Path.home() / ".praisonai" / "langfuse.env"
    if config_file.exists():
        # Load env file into current process environment
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
        console.print(f"[dim]📄 Loaded config from {config_file}[/dim]")
    
    config = LangfuseSinkConfig()
    
    if not config.enabled:
        console.print("[yellow]⚠️  Langfuse tracing is disabled[/yellow]")
        console.print("Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY environment variables")
        return
    
    console.print("[blue]🧪 Testing Langfuse connectivity...[/blue]")
    console.print(f"[dim]Host: {config.host}[/dim]")
    console.print(f"[dim]Public Key: {config.public_key[:8]}...[/dim]")
    
    try:
        # Create sink and emitter
        sink = LangfuseSink(config)
        emitter = TraceEmitter(sink=sink, enabled=True)
        
        # Emit test events
        agent_name = "test-agent"
        timestamp = time.time()
        
        console.print("[yellow]📤 Emitting test events...[/yellow]")
        
        # Agent start
        emitter.agent_start(agent_name, metadata={"test": True, "cli": "praisonai langfuse test"})
        
        # Tool call
        emitter.tool_start("test_tool", {"query": "Hello, Langfuse!"}, agent_name=agent_name)
        time.sleep(0.1)  # Simulate work
        emitter.tool_end(
            "test_tool", 
            duration_ms=100, 
            status="ok", 
            result_summary="Test completed successfully",
            agent_name=agent_name
        )
        
        # Output
        emitter.output("Test trace emitted successfully!", agent_name=agent_name)
        
        # Agent end
        emitter.agent_end(agent_name, status="ok")
        
        # Flush and close
        emitter.flush()
        emitter.close()
        
        console.print("[green]✅ Test trace sent successfully![/green]")
        console.print(f"[blue]🌐 Check your Langfuse dashboard: {config.host}[/blue]")
        console.print("[dim]It may take a few seconds for the trace to appear[/dim]")
        
    except Exception as e:
        console.print(f"[red]❌ Test failed: {e}[/red]")
        raise typer.Abort()


@app.command("version")
def langfuse_version():
    """Show Langfuse version information."""
    console = Console()
    
    try:
        import langfuse
        console.print(f"[bold]Langfuse SDK[/bold]: {langfuse.__version__}")
    except ImportError:
        console.print("[yellow]Langfuse SDK not installed[/yellow]")
        console.print("[blue]Install with: pip install praisonai[langfuse][/blue]")
    except AttributeError:
        console.print("[yellow]Langfuse SDK version unknown[/yellow]")
    
    # Check local server version if running
    data_dir = os.path.expanduser("~/.praisonai/langfuse")
    repo_path = Path(data_dir) / "langfuse"
    
    if repo_path.exists():
        try:
            result = subprocess.run([
                "git", "describe", "--tags", "--abbrev=0"
            ], cwd=repo_path, capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.strip()
                console.print(f"[bold]Local Langfuse[/bold]: {version}")
        except Exception:
            pass