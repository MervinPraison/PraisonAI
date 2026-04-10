"""PraisonAI Langfuse — Observability platform for LLM apps.

Provides `praisonai langfuse` CLI commands to manage local (Docker) and remote
Langfuse instances for observability and evaluation of agent workflows.
"""

import os
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

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
    email: str = typer.Option(
        None, "--email", "-e", help="Initial admin email (default: admin@langfuse.com)"
    ),
    password: str = typer.Option(
        None, "--password", "-pw", help="Initial admin password (default: admin12345)"
    ),
):
    """Start local Langfuse server (Docker).
    
    Clones Langfuse repo and starts the full Docker Compose stack
    with web UI, worker, PostgreSQL, ClickHouse, Redis, and MinIO.
    
    Examples:
        praisonai langfuse
        praisonai langfuse --port 8080
        praisonai langfuse --no-detach
        praisonai langfuse --email admin@example.com --password mypassword123
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
    
    # Set up initial credentials via .env file
    env_file = repo_path / ".env"
    env_vars = {}
    
    # Read existing .env if present
    if env_file.exists():
        for line in env_file.read_text().strip().split('\n'):
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    
    # Set default or custom credentials
    default_email = email or "admin@langfuse.com"
    default_password = password or "admin12345"
    default_name = "Admin User"
    
    # Update with Langfuse init user environment variables
    env_vars["LANGFUSE_INIT_USER_EMAIL"] = default_email
    env_vars["LANGFUSE_INIT_USER_PASSWORD"] = default_password
    env_vars["LANGFUSE_INIT_USER_NAME"] = default_name
    env_vars["LANGFUSE_INIT_ORG_NAME"] = "Default Org"
    env_vars["LANGFUSE_INIT_PROJECT_NAME"] = "Default Project"
    
    # Write .env file
    env_content = "# Langfuse Initial User Configuration\n"
    env_content += f"LANGFUSE_INIT_USER_EMAIL={default_email}\n"
    env_content += f"LANGFUSE_INIT_USER_PASSWORD={default_password}\n"
    env_content += f"LANGFUSE_INIT_USER_NAME={default_name}\n"
    env_content += f"LANGFUSE_INIT_ORG_NAME=Default Org\n"
    env_content += f"LANGFUSE_INIT_PROJECT_NAME=Default Project\n"
    env_content += "LANGFUSE_INIT_PROJECT_ID=default-project\n"
    env_file.write_text(env_content)
    
    console.print(f"[dim]📄 Initial user: {default_email}[/dim]")
    
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
            console.print(f"[dim]Login: {default_email} / {default_password[:3]}***[/dim]")
            console.print()
            console.print("[bold]Next steps:[/bold]")
            console.print("1. Open the web UI and login")
            console.print("2. Get API keys from Settings > API Keys")
            console.print("3. Configure PraisonAI:")
            console.print(f"   [green]praisonai langfuse config --public-key pk-... --secret-key sk-...[/green]")
            console.print("4. Test: [green]praisonai langfuse test[/green]")
            
        else:
            subprocess.run(cmd, cwd=repo_path)
            
    except subprocess.CalledProcessError as e:
        error_output = str(e)
        if hasattr(e, 'stderr') and e.stderr:
            error_output += e.stderr
        if hasattr(e, 'stdout') and e.stdout:
            error_output += e.stdout
        
        # Check for port conflicts
        from praisonai.cli.commands.port import _is_port_conflict_error, _extract_port_from_error, _show_port_conflict_help
        if _is_port_conflict_error(error_output):
            port = _extract_port_from_error(error_output)
            if port:
                _show_port_conflict_help(port, console)
            else:
                console.print(f"[red]❌ Failed to start Langfuse: Port conflict detected[/red]")
                console.print("[yellow]Run [cyan]praisonai port list[/cyan] to see ports in use[/yellow]")
        else:
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


@app.command("init")
def langfuse_init(
    email: str = typer.Option(
        "admin@langfuse.com", "--email", "-e", help="Admin email address"
    ),
    password: str = typer.Option(
        None, "--password", "-p", help="Admin password (will prompt if not provided)"
    ),
    port: int = typer.Option(3000, "--port", "-p", help="Port to listen on"),
    data_dir: str = typer.Option(
        None, "--data-dir", help="Data directory (default: ~/.praisonai/langfuse)"
    ),
):
    """Initialize Langfuse with custom admin credentials.
    
    First-time setup with configurable admin user. Sets up the Docker
    environment and creates initial user account.
    
    Examples:
        praisonai langfuse init
        praisonai langfuse init --email admin@example.com --password mypass123
        praisonai langfuse init --email user@company.com --port 8080
    """
    console = Console()
    
    # Prompt for password if not provided
    if password is None:
        password = typer.prompt("Enter admin password", hide_input=True)
        password_confirm = typer.prompt("Confirm password", hide_input=True)
        if password != password_confirm:
            console.print("[red]❌ Passwords do not match[/red]")
            raise typer.Abort()
    
    # Validate password length (Langfuse requires 8+ characters)
    if len(password) < 8:
        console.print("[red]❌ Password must be at least 8 characters long[/red]")
        raise typer.Abort()
    
    console.print("[bold]🚀 Initializing Langfuse...[/bold]")
    console.print(f"[dim]Email: {email}[/dim]")
    console.print(f"[dim]Port: {port}[/dim]")
    console.print()
    
    # Reuse the start logic with explicit credentials
    ctx = typer.Context(langfuse_start)
    langfuse_start(
        ctx=ctx,
        port=port,
        host="127.0.0.1",
        detach=True,
        data_dir=data_dir,
        email=email,
        password=password
    )


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
        console.print("[yellow]ℹ️  No configuration options provided[/yellow]")
        console.print()
        console.print("[bold]Quick Setup Guide:[/bold]")
        console.print()
        console.print("1. [bold cyan]Get your API keys from Langfuse Cloud:[/bold cyan]")
        console.print("   [blue]https://cloud.langfuse.com[/blue]")
        console.print("   → Sign up → Create project → Project Settings → API Keys")
        console.print()
        console.print("2. [bold cyan]Configure PraisonAI:[/bold cyan]")
        console.print("   [dim]praisonai langfuse config[/dim]")
        console.print("     [dim]--public-key pk-...[/dim]")
        console.print("     [dim]--secret-key sk-...[/dim]")
        console.print()
        console.print("3. [bold cyan]Verify your setup:[/bold cyan]")
        console.print("   [green]praisonai langfuse test[/green]")
        console.print()
        console.print("[dim]Use --show to view current configuration[/dim]")
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
        console.print("[yellow]⚠️  Langfuse credentials not configured[/yellow]")
        console.print()
        console.print("[bold]How to get your Langfuse API keys:[/bold]")
        console.print("1. Go to [blue]https://cloud.langfuse.com[/blue] and sign up/login")
        console.print("2. Create a new project (or open existing)")
        console.print("3. Go to Project Settings → API Keys")
        console.print("4. Click 'Create new API keys'")
        console.print()
        console.print("[bold]Then configure PraisonAI:[/bold]")
        console.print("  [green]praisonai langfuse config --public-key=pk-... --secret-key=sk-...[/green]")
        console.print()
        console.print("Or set environment variables:")
        console.print("  [green]export LANGFUSE_PUBLIC_KEY=pk-...[/green]")
        console.print("  [green]export LANGFUSE_SECRET_KEY=sk-...[/green]")
        raise typer.Abort()
    
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


@app.command("traces")
def langfuse_traces(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of traces to show"),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="Filter by session ID"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Filter by agent name"),
):
    """
    List traces from Langfuse.
    
    Fetches and displays traces from the Langfuse API without opening the web UI.
    Shows trace ID, name, timestamp, session, and metadata.
    
    Examples:
        praisonai langfuse traces
        praisonai langfuse traces --limit 10
        praisonai langfuse traces --session abc-123
        praisonai langfuse traces --agent MyAgent
    """
    console = Console()
    
    # Import the client
    try:
        from ..langfuse_client import LangfuseClient, LangfuseAPIError
    except ImportError:
        console.print("[red]❌ Langfuse client not available[/red]")
        raise typer.Abort()
    
    # Load client from config
    try:
        client = LangfuseClient.from_config_file()
    except FileNotFoundError as e:
        console.print(f"[red]❌ {e}[/red]")
        console.print("[yellow]Run 'praisonai langfuse config --public-key ... --secret-key ...' first[/yellow]")
        raise typer.Abort()
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Abort()
    
    # Fetch traces
    try:
        console.print(f"[blue]📊 Fetching traces from {client.host}...[/blue]")
        traces = client.get_traces(limit=limit, session_id=session_id, name=agent)
        
        if not traces:
            console.print("[yellow]No traces found[/yellow]")
            if session_id:
                console.print(f"[dim]Filter: session_id={session_id}[/dim]")
            if agent:
                console.print(f"[dim]Filter: agent={agent}[/dim]")
            return
        
        # Create table
        table = Table(title=f"Recent Traces ({len(traces)})")
        table.add_column("Trace ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("Timestamp", style="blue")
        table.add_column("Session", style="yellow")
        table.add_column("Observations", style="magenta")
        
        for trace in traces:
            trace_id = trace.get("id", "unknown")[:12] + "..."
            name = trace.get("name", "unnamed")
            
            # Parse timestamp
            ts = trace.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    timestamp = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    timestamp = str(ts)[:16]
            else:
                timestamp = "unknown"
            
            session = trace.get("sessionId", "")[:8] + "..." if trace.get("sessionId") else "-"
            obs_count = len(trace.get("observations", []))
            
            table.add_row(trace_id, name, timestamp, session, str(obs_count))
        
        console.print(table)
        
        # Show hint for viewing details
        if traces:
            console.print(f"[dim]View details: praisonai langfuse show {traces[0].get('id')}[/dim]")
        
    except LangfuseAPIError as e:
        console.print(f"[red]❌ API Error: {e}[/red]")
        if "401" in str(e):
            console.print("[yellow]Check your LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY[/yellow]")
        elif "connection" in str(e).lower():
            console.print("[yellow]Ensure Langfuse is running: praisonai langfuse status[/yellow]")
        raise typer.Abort()
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        raise typer.Abort()


@app.command("sessions")
def langfuse_sessions(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of sessions to show"),
):
    """
    List sessions from Langfuse.
    
    Fetches and displays sessions (conversation threads) from the Langfuse API.
    Shows session ID, creation time, and number of traces in each session.
    
    Examples:
        praisonai langfuse sessions
        praisonai langfuse sessions --limit 10
    """
    console = Console()
    
    # Import the client
    try:
        from ..langfuse_client import LangfuseClient, LangfuseAPIError
    except ImportError:
        console.print("[red]❌ Langfuse client not available[/red]")
        raise typer.Abort()
    
    # Load client from config
    try:
        client = LangfuseClient.from_config_file()
    except FileNotFoundError as e:
        console.print(f"[red]❌ {e}[/red]")
        console.print("[yellow]Run 'praisonai langfuse config --public-key ... --secret-key ...' first[/yellow]")
        raise typer.Abort()
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Abort()
    
    # Fetch sessions
    try:
        console.print(f"[blue]📊 Fetching sessions from {client.host}...[/blue]")
        sessions = client.get_sessions(limit=limit)
        
        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
            return
        
        # Create table
        table = Table(title=f"Sessions ({len(sessions)})")
        table.add_column("Session ID", style="cyan", no_wrap=True)
        table.add_column("Created", style="blue")
        table.add_column("Traces", style="green", justify="right")
        
        for session in sessions:
            session_id = session.get("id", "unknown")[:16] + "..."
            
            # Parse timestamp
            ts = session.get("createdAt", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    created = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    created = str(ts)[:16]
            else:
                created = "unknown"
            
            trace_count = session.get("traceCount", len(session.get("traces", [])))
            
            table.add_row(session_id, created, str(trace_count))
        
        console.print(table)
        
        # Show hint
        if sessions:
            console.print(f"[dim]View traces in session: praisonai langfuse traces --session {sessions[0].get('id')}[/dim]")
        
    except LangfuseAPIError as e:
        console.print(f"[red]❌ API Error: {e}[/red]")
        if "401" in str(e):
            console.print("[yellow]Check your LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY[/yellow]")
        elif "connection" in str(e).lower():
            console.print("[yellow]Ensure Langfuse is running: praisonai langfuse status[/yellow]")
        raise typer.Abort()
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        raise typer.Abort()


@app.command("show")
def langfuse_show(
    trace_id: str = typer.Argument(..., help="Trace ID to display"),
):
    """
    Show detailed information about a specific trace.
    
    Displays full trace details including metadata, input/output, and all
    observations (spans, events, generations) without opening the web UI.
    
    Examples:
        praisonai langfuse show trace-abc-123
        praisonai langfuse show --help
    """
    console = Console()
    
    # Import the client
    try:
        from ..langfuse_client import LangfuseClient, LangfuseAPIError
    except ImportError:
        console.print("[red]❌ Langfuse client not available[/red]")
        raise typer.Abort()
    
    # Load client from config
    try:
        client = LangfuseClient.from_config_file()
    except FileNotFoundError as e:
        console.print(f"[red]❌ {e}[/red]")
        console.print("[yellow]Run 'praisonai langfuse config --public-key ... --secret-key ...' first[/yellow]")
        raise typer.Abort()
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Abort()
    
    # Fetch trace details
    try:
        console.print(f"[blue]🔍 Fetching trace {trace_id}...[/blue]")
        trace = client.get_trace(trace_id)
        
        # Display trace info
        console.print()
        console.print(Panel(f"[bold cyan]Trace: {trace.get('name', 'unnamed')}[/bold cyan]", 
                           subtitle=f"ID: {trace_id}"))
        
        # Metadata
        meta_table = Table(show_header=False, box=None)
        meta_table.add_column("Key", style="yellow")
        meta_table.add_column("Value", style="white")
        
        # Parse timestamp
        ts = trace.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                timestamp = str(ts)
        else:
            timestamp = "unknown"
        
        meta_table.add_row("Timestamp:", timestamp)
        meta_table.add_row("Session:", trace.get("sessionId", "-"))
        meta_table.add_row("User:", trace.get("userId", "-"))
        
        if trace.get("metadata"):
            meta_str = json.dumps(trace.get("metadata"), indent=2)
            meta_table.add_row("Metadata:", meta_str)
        
        console.print(meta_table)
        
        # Observations
        observations = trace.get("observations", [])
        if observations:
            console.print()
            console.print(f"[bold]Observations ({len(observations)}):[/bold]")
            
            obs_table = Table()
            obs_table.add_column("Type", style="cyan")
            obs_table.add_column("Name", style="green")
            obs_table.add_column("Start Time", style="blue")
            obs_table.add_column("Status", style="yellow")
            
            for obs in observations:
                obs_type = obs.get("type", "unknown")
                name = obs.get("name", "unnamed")
                
                # Parse start time
                start_ts = obs.get("startTime", "")
                if start_ts:
                    try:
                        dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                        start_time = dt.strftime("%H:%M:%S")
                    except Exception:
                        start_time = str(start_ts)[11:19]
                else:
                    start_time = "-"
                
                status = obs.get("level", "DEFAULT")
                if obs.get("statusMessage"):
                    status = f"{status} ({obs.get('statusMessage')})"
                
                obs_table.add_row(obs_type, name, start_time, status)
            
            console.print(obs_table)
        
        # Input/Output (if available)
        if trace.get("input"):
            console.print()
            console.print("[bold]Input:[/bold]")
            input_str = json.dumps(trace.get("input"), indent=2)
            console.print(f"[dim]{input_str[:500]}[/dim]")
        
        if trace.get("output"):
            console.print()
            console.print("[bold]Output:[/bold]")
            output_str = json.dumps(trace.get("output"), indent=2)
            console.print(f"[dim]{output_str[:500]}[/dim]")
        
        console.print()
        console.print(f"[dim]View in UI: {client.host}/trace/{trace_id}[/dim]")
        
    except LangfuseAPIError as e:
        if "404" in str(e) or "not found" in str(e).lower():
            console.print(f"[red]❌ Trace not found: {trace_id}[/red]")
        else:
            console.print(f"[red]❌ API Error: {e}[/red]")
        raise typer.Abort()
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        raise typer.Abort()