"""
Unified Dashboard — launch all PraisonAI UIs from a single interface.

Usage:
    praisonai unified                 # Dashboard on :3000
    praisonai unified --port 9000     # Custom port
"""

import subprocess
import sys
import atexit
import signal
import json
from pathlib import Path
from types import FrameType
from typing import Set, TextIO
import socket
import time

import typer

app = typer.Typer(help="🌟 Unified Dashboard (Flow + Claw + UI)")

# Port mappings - centralized configuration
SERVICE_PORTS = {
    "flow": 7860,
    "claw": 8082, 
    "ui": 8081
}

# Global process tracking for cleanup
_ACTIVE_PROCESSES: Set[subprocess.Popen] = set()
_PROCESS_LOG_HANDLES: dict[subprocess.Popen, TextIO] = {}

def _cleanup_processes():
    """Cleanup all spawned processes on exit."""
    for proc in _ACTIVE_PROCESSES.copy():
        try:
            if proc.poll() is None:  # Process still running
                proc.terminate()
                proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        log_handle = _PROCESS_LOG_HANDLES.pop(proc, None)
        if log_handle:
            try:
                log_handle.close()
            except Exception:
                pass
        _ACTIVE_PROCESSES.discard(proc)

def _resolve_check_host(host: str) -> str:
    return "127.0.0.1" if host == "0.0.0.0" else host


def _handle_shutdown_signal(signum: int, frame: FrameType | None):
    _cleanup_processes()
    sys.exit(0)


def _register_cleanup_handlers():
    """Register cleanup handlers for current process only."""
    # Save original handlers to restore later
    original_sigint = signal.signal(signal.SIGINT, _handle_shutdown_signal)
    original_sigterm = signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    atexit.register(_cleanup_processes)
    return original_sigint, original_sigterm

def _unregister_cleanup_handlers(original_sigint, original_sigterm):
    """Restore original signal handlers."""
    signal.signal(signal.SIGINT, original_sigint)
    signal.signal(signal.SIGTERM, original_sigterm)
    # Note: atexit handlers cannot be easily unregistered in Python < 3.9
    # so we keep the atexit handler but check if process list is empty


def _auto_start_services(console, host: str):
    """Auto-start PraisonAI services like the 'up' command does."""

    # Services to start
    services = [
        ("flow", 7860),
        ("claw", 8082),
        ("ui", 8081)
    ]
    
    for service_name, service_port in services:
        # Check if service is already running
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        check_host = "127.0.0.1" if host == "0.0.0.0" else host
        try:
            connection_result = sock.connect_ex((check_host, service_port))
            if connection_result == 0:
                console.print(f"[yellow]✓ {service_name} already running on port {service_port}[/yellow]")
                sock.close()
                continue
        except OSError:
            pass
        finally:
            sock.close()
        
        # Start the service
        console.print(f"[cyan]Starting {service_name} on port {service_port}...[/cyan]")
        try:
            # Create log directory for troubleshooting
            log_dir = Path.home() / ".praisonai" / "unified" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{service_name}.log"
            
            log_handle = open(log_file, "a", encoding="utf-8")
            try:
                if service_name == "flow":
                    proc = subprocess.Popen([
                        sys.executable, "-m", "praisonai", "flow", 
                        "--port", str(service_port), "--host", host, "--no-open"
                    ], stdout=log_handle, stderr=subprocess.STDOUT)
                elif service_name == "claw":
                    proc = subprocess.Popen([
                        sys.executable, "-m", "praisonai", "claw",
                        "--port", str(service_port), "--host", host
                    ], stdout=log_handle, stderr=subprocess.STDOUT)
                elif service_name == "ui":
                    proc = subprocess.Popen([
                        sys.executable, "-m", "praisonai", "ui",
                        "--port", str(service_port), "--host", host
                    ], stdout=log_handle, stderr=subprocess.STDOUT)
                
                # Track process for cleanup
                _ACTIVE_PROCESSES.add(proc)
                _PROCESS_LOG_HANDLES[proc] = log_handle
                
                # Wait briefly for service to start
                time.sleep(1.5)
                
                # Check if process is still alive
                if proc.poll() is not None:
                    console.print(f"[red]✗ {service_name} failed to start (exit code: {proc.returncode})[/red]")
                    console.print(f"[dim]Check log: {log_file}[/dim]")
                    # Clean up failed process
                    _ACTIVE_PROCESSES.discard(proc)
                    if proc in _PROCESS_LOG_HANDLES:
                        _PROCESS_LOG_HANDLES.pop(proc).close()
                else:
                    console.print(f"[green]✓ {service_name} started successfully[/green]")
            except Exception:
                log_handle.close()
                raise
                    
        except Exception as e:
            console.print(f"[red]✗ Failed to start {service_name}: {e}[/red]")


def _run_aiui_dashboard(port: int, host: str, console):
    """Run the aiui dashboard interface."""
    console.print("[bold green]🦞 Starting aiui Dashboard...[/bold green]")
    
    try:
        # Try to import and run aiui directly
        import tempfile
        import os
        
        # Create a temporary script for aiui dashboard
        aiui_script = f'''
import praisonaiui as aiui

# Configure aiui for dashboard style
aiui.set_style("dashboard")
aiui.set_branding(title="PraisonAI Unified Dashboard", logo="🌟")

# Set up pages for unified dashboard
aiui.set_pages([
    "chat", "agents", "memory", "knowledge", 
    "skills", "sessions", "usage", "config", "logs"
])

# Register a simple reply handler
@aiui.reply
async def on_reply(message):
    return f"Unified Dashboard: {{message.content}}"

# Register a welcome message
@aiui.welcome
async def on_welcome():
    return "Welcome to PraisonAI Unified Dashboard! 🌟"

# Start aiui server
if __name__ == "__main__":
    import uvicorn
    app = aiui.create_app()
    uvicorn.run(app, host={json.dumps(host)}, port={int(port)})
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(aiui_script)
            temp_script = f.name
        
        try:
            console.print(f"[green]✓ Starting aiui dashboard on {host}:{port}[/green]")
            
            # Check if aiui is available first
            result = subprocess.run([
                sys.executable, "-c", "import praisonaiui"
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                console.print("[red]Error: aiui package not installed.[/red]")
                console.print("[yellow]Install with: pip install aiui[/yellow]")
                return False
            
            # Run the aiui script
            subprocess.run([sys.executable, temp_script], check=True)
            
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_script)
            except:
                pass
        
    except ImportError:
        console.print("[red]Error: aiui package not installed.[/red]")
        console.print("[yellow]Install with: pip install aiui[/yellow]")
        return False
    except subprocess.CalledProcessError as e:
        console.print(f"[red]aiui dashboard exited with code {e.returncode}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Error running aiui dashboard: {e}[/red]")
        return False
    
    return True


def _generate_dashboard_html(host: str = "localhost") -> str:
    """Generate dashboard HTML with dynamic host configuration."""
    dashboard_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PraisonAI Unified Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
        }
        
        .header {
            padding: 2rem;
            text-align: center;
            background: rgba(0, 0, 0, 0.1);
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }
        
        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }
        
        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 2rem;
            padding: 2rem;
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .card {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 15px;
            padding: 2rem;
            text-align: center;
            transition: all 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-5px);
            background: rgba(255, 255, 255, 0.15);
        }
        
        .card h2 {
            font-size: 1.8rem;
            margin-bottom: 1rem;
            color: #fff;
        }
        
        .card p {
            margin-bottom: 1.5rem;
            opacity: 0.9;
            line-height: 1.6;
        }
        
        .btn {
            display: inline-block;
            padding: 12px 30px;
            background: rgba(255, 255, 255, 0.2);
            color: white;
            text-decoration: none;
            border-radius: 25px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            transition: all 0.3s ease;
            margin: 0.5rem;
        }
        
        .btn:hover {
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
            transform: scale(1.05);
        }
        
        .btn.primary {
            background: #4CAF50;
            border-color: #4CAF50;
        }
        
        .btn.primary:hover {
            background: #45a049;
            border-color: #45a049;
        }
        
        .status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.9rem;
            margin-left: 1rem;
        }
        
        .status.running {
            background: #4CAF50;
            color: white;
        }
        
        .status.stopped {
            background: #f44336;
            color: white;
        }
        
        .footer {
            text-align: center;
            padding: 2rem;
            opacity: 0.7;
        }
        
        iframe {
            width: 100%;
            height: 80vh;
            border: none;
            border-radius: 15px;
            background: white;
        }
        
        .iframe-container {
            display: none;
            padding: 2rem;
        }
        
        .back-btn {
            position: fixed;
            top: 2rem;
            left: 2rem;
            z-index: 1000;
        }
        
        @media (max-width: 768px) {
            .dashboard {
                grid-template-columns: 1fr;
                padding: 1rem;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .card {
                padding: 1.5rem;
            }
        }
    </style>
</head>
<body>
    <div id="dashboard-view">
        <div class="header">
            <h1>🌟 PraisonAI Unified Dashboard</h1>
            <p>Access all your AI tools from one place</p>
        </div>
        
        <div class="dashboard">
            <div class="card">
                <h2>🎯 Flow Visual Builder</h2>
                <p>Create AI workflows visually with drag-and-drop interface powered by Langflow.</p>
                <a href="#" onclick="openService('flow', 7860)" class="btn primary">Launch Flow Builder</a>
                <span id="flow-status" class="status stopped">Stopped</span>
                <p style="margin-top: 1rem; font-size: 0.9rem; opacity: 0.8;">
                    Build agent workflows, connect tools, design complex AI pipelines.
                </p>
            </div>
            
            <div class="card">
                <h2>🦞 Claw Dashboard</h2>
                <p>Full-featured dashboard with agents, memory, knowledge, and integrations.</p>
                <a href="#" onclick="openService('claw', 8082)" class="btn primary">Launch Dashboard</a>
                <span id="claw-status" class="status stopped">Stopped</span>
                <p style="margin-top: 1rem; font-size: 0.9rem; opacity: 0.8;">
                    Manage agents, view memory, connect Telegram/Discord bots.
                </p>
            </div>
            
            <div class="card">
                <h2>🤖 Clean Chat UI</h2>
                <p>Simple, distraction-free chat interface for direct agent conversations.</p>
                <a href="#" onclick="openService('ui', 8081)" class="btn primary">Launch Chat</a>
                <span id="ui-status" class="status stopped">Stopped</span>
                <p style="margin-top: 1rem; font-size: 0.9rem; opacity: 0.8;">
                    Pure chat experience - no sidebars, just you and your AI agent.
                </p>
            </div>
        </div>
        
        <div class="footer">
            <p>🚀 PraisonAI - Making AI Agent Development Simple</p>
        </div>
    </div>
    
    <div id="iframe-view" class="iframe-container">
        <a href="#" onclick="showDashboard()" class="btn back-btn">← Back to Dashboard</a>
        <iframe id="service-iframe" src=""></iframe>
    </div>
    
    <script>
        let activeServices = {};
        
        async function checkServiceStatus(service, port) {
            try {
                const serviceHost = window.location.hostname || '127.0.0.1';
                const response = await fetch(`http://${serviceHost}:${port}`, {
                    method: 'GET',
                    mode: 'no-cors'
                });
                return true;
            } catch (e) {
                return false;
            }
        }
        
        async function startService(service) {
            const response = await fetch(`/start/${service}`, {
                method: 'POST'
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to start service');
            }
            
            return await response.json();
        }
        
        async function openService(service, port) {
            const statusEl = document.getElementById(`${service}-status`);
            statusEl.textContent = 'Starting...';
            statusEl.className = 'status';
            
            try {
                // Try to start the service
                const result = await startService(service);
                
                if (result.success) {
                    // Wait a moment for the service to fully start
                    await new Promise(resolve => setTimeout(resolve, 3000));
                    
                    // Open in iframe using dynamic hostname
                    document.getElementById('dashboard-view').style.display = 'none';
                    document.getElementById('iframe-view').style.display = 'block';
                    const serviceHost = window.location.hostname || '127.0.0.1';
                    document.getElementById('service-iframe').src = `http://${serviceHost}:${port}`;
                    
                    statusEl.textContent = 'Running';
                    statusEl.className = 'status running';
                    activeServices[service] = port;
                } else {
                    statusEl.textContent = 'Failed to Start';
                    statusEl.className = 'status stopped';
                    alert(`Failed to start ${service}: ${result.error || 'Unknown error'}`);
                }
            } catch (error) {
                statusEl.textContent = 'Failed to Start';
                statusEl.className = 'status stopped';
                alert(`Failed to start ${service}: ${error.message}`);
            }
        }
        
        function showDashboard() {
            document.getElementById('dashboard-view').style.display = 'block';
            document.getElementById('iframe-view').style.display = 'none';
            document.getElementById('service-iframe').src = '';
        }
        
        // Check initial service status
        async function updateStatuses() {
            const services = [
                ['flow', 7860],
                ['claw', 8082], 
                ['ui', 8081]
            ];
            
            for (const [service, port] of services) {
                const isRunning = await checkServiceStatus(service, port);
                const statusEl = document.getElementById(`${service}-status`);
                if (isRunning) {
                    statusEl.textContent = 'Running';
                    statusEl.className = 'status running';
                    activeServices[service] = port;
                } else {
                    statusEl.textContent = 'Stopped';
                    statusEl.className = 'status stopped';
                    delete activeServices[service];
                }
            }
        }
        
        // Update status every 10 seconds
        setInterval(updateStatuses, 10000);
        updateStatuses(); // Initial check
    </script>
</body>
</html>"""
    return dashboard_html


@app.callback(invoke_without_command=True)
def unified(
    ctx: typer.Context,
    port: int = typer.Option(3000, "--port", "-p", help="Port to run unified dashboard on"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to (use 0.0.0.0 to expose remotely)"),
    auto_start: bool = typer.Option(True, "--auto-start/--no-auto-start", help="Auto-start all services"),
    aiui: bool = typer.Option(False, "--aiui", help="Use aiui dashboard interface (experimental)"),
):
    """
    Launch the PraisonAI Unified Dashboard.
    
    Provides a single interface at localhost:3000 to access:
    - Flow Visual Builder (Langflow) - port 7860
    - Claw Dashboard (Full UI) - port 8082  
    - Clean Chat UI - port 8081
    
    This unified launcher:
    1. Auto-starts all services by default (like 'praisonai up')
    2. Creates agents visually using Flow Builder
    3. Chats with agents using the Chat UI
    4. Manages everything from Claw Dashboard
    5. Connects external services like Telegram
    6. Optionally uses aiui for enhanced dashboard experience
    
    Examples:
        praisonai dashboard                           # Auto-start all services
        praisonai dashboard --no-auto-start          # Dashboard only (no auto-start)
        praisonai dashboard --port 9000 --host 0.0.0.0
        praisonai dashboard --aiui                   # Use aiui interface (experimental)
    """
    if ctx.invoked_subcommand is not None:
        return
    
    from rich.console import Console
    console = Console()
    
    # Check for aiui mode first
    if aiui:
        return _run_aiui_dashboard(port, host, console)
    
    # Import optional dependencies inside function to avoid startup overhead
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import HTMLResponse
        import uvicorn
    except ImportError as exc:
        console.print(f"[red]Error: Missing optional dependencies for unified dashboard.[/red]")
        console.print(f"[yellow]Install with: pip install 'praisonai[api]'[/yellow]")
        console.print(f"[dim]Error details: {exc}[/dim]")
        raise typer.Abort()
    
    # Auto-start services if enabled
    if auto_start:
        console.print("[bold green]🚀 Auto-starting PraisonAI services...[/bold green]")
        _auto_start_services(console, host)
        console.print("[green]✅ Auto-start complete[/green]")
        console.print()
    
    # Register cleanup handlers and save originals for restoration
    original_handlers = _register_cleanup_handlers()
    
    # Create FastAPI app
    fastapi_app = FastAPI(title="PraisonAI Unified Dashboard")
    
    @fastapi_app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return _generate_dashboard_html(host)
    
    @fastapi_app.post("/start/{service}")
    async def start_service(service: str):
        """Start a PraisonAI service with proper startup verification."""
        if service not in SERVICE_PORTS:
            raise HTTPException(status_code=400, detail=f"Unknown service: {service}")
        
        service_port = SERVICE_PORTS[service]
        check_host = _resolve_check_host(host)
        
        # Check if service is already running
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            connection_result = sock.connect_ex((check_host, service_port))
            if connection_result == 0:
                return {"success": True, "message": f"Service {service} already running on port {service_port}"}
        except OSError:
            pass
        finally:
            sock.close()
        
        log_handle = None
        proc = None
        try:
            # Create log directory for troubleshooting
            log_dir = Path.home() / ".praisonai" / "unified" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{service}.log"
            log_handle = open(log_file, "a", encoding="utf-8")
            
            if service == "flow":
                # Use praisonai module entrypoint so command resolution matches CLI behavior.
                proc = subprocess.Popen([
                    sys.executable, "-m", "praisonai", "flow", 
                    "--port", str(service_port), "--host", host, "--no-open"
                ], stdout=log_handle, stderr=subprocess.STDOUT)
            elif service == "claw":
                proc = subprocess.Popen([
                    sys.executable, "-m", "praisonai", "claw",
                    "--port", str(service_port), "--host", host
                ], stdout=log_handle, stderr=subprocess.STDOUT)
            elif service == "ui":
                proc = subprocess.Popen([
                    sys.executable, "-m", "praisonai", "ui",
                    "--port", str(service_port), "--host", host
                ], stdout=log_handle, stderr=subprocess.STDOUT)
            
            # Wait for service to start with timeout
            deadline = time.time() + 15
            service_ready = False
            
            while time.time() < deadline:
                if proc.poll() is not None:
                    # Process exited early, service failed to start
                    if log_handle and not log_handle.closed:
                        log_handle.close()
                    _ACTIVE_PROCESSES.discard(proc)
                    _PROCESS_LOG_HANDLES.pop(proc, None)
                    raise HTTPException(
                        status_code=500,
                        detail=f"{service} exited during startup (exit code: {proc.returncode}). Check {log_file}"
                    )
                
                # Check if port is accepting connections
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    if test_sock.connect_ex((check_host, service_port)) == 0:
                        service_ready = True
                        break
                except OSError:
                    pass
                finally:
                    test_sock.close()
                
                time.sleep(0.5)
            
            if not service_ready:
                # Service didn't become ready in time
                proc.terminate()
                proc.wait(timeout=5)
                if log_handle and not log_handle.closed:
                    log_handle.close()
                _ACTIVE_PROCESSES.discard(proc)
                _PROCESS_LOG_HANDLES.pop(proc, None)
                raise HTTPException(
                    status_code=504,
                    detail=f"{service} did not become ready within 15 seconds. Check {log_file}"
                )
            
            # Track process for cleanup only after successful startup
            _ACTIVE_PROCESSES.add(proc)
            _PROCESS_LOG_HANDLES[proc] = log_handle
            
            return {"success": True, "message": f"Started {service} on port {service_port}"}
            
        except HTTPException:
            raise
        except Exception as e:
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass
                _ACTIVE_PROCESSES.discard(proc)
                _PROCESS_LOG_HANDLES.pop(proc, None)
            if log_handle and not log_handle.closed:
                log_handle.close()
            raise HTTPException(status_code=500, detail=f"Failed to start {service}: {str(e)}")
    
    @fastapi_app.get("/health")
    async def health():
        return {"status": "healthy", "service": "unified-dashboard"}
    
    console.print()
    console.print("[bold green]🌟 Starting PraisonAI Unified Dashboard[/bold green]")
    console.print(f"[dim]Unified interface on {host}:{port}[/dim]")
    if auto_start:
        console.print("[dim]Services auto-started and dashboard ready[/dim]")
    console.print("[dim]Access Flow Builder, Claw Dashboard, and Chat UI from one place[/dim]")
    console.print()
    
    try:
        uvicorn.run(
            fastapi_app,
            host=host,
            port=port,
            log_level="info"
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]🌟 Unified Dashboard stopped.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error starting unified dashboard: {e}[/red]")
        raise typer.Abort()
    finally:
        # Restore original signal handlers
        _unregister_cleanup_handlers(*original_handlers)
        _cleanup_processes()
