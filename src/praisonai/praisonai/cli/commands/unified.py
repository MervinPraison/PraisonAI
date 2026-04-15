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
from pathlib import Path
from typing import Set

import typer

# Lazy imports for optional dependencies
_FASTAPI_IMPORT_ERROR = None

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
    import uvicorn
except ImportError as exc:
    _FASTAPI_IMPORT_ERROR = exc
    FastAPI = None
    HTTPException = None
    HTMLResponse = None
    uvicorn = None

app = typer.Typer(help="🌟 Unified PraisonAI Interface (Flow + Claw + UI)")

# Port mappings - centralized configuration
SERVICE_PORTS = {
    "flow": 7860,
    "claw": 8082, 
    "ui": 8081
}

# Global process tracking for cleanup
_ACTIVE_PROCESSES: Set[subprocess.Popen] = set()

def _cleanup_processes():
    """Cleanup all spawned processes on exit."""
    for proc in _ACTIVE_PROCESSES.copy():
        try:
            if proc.poll() is None:  # Process still running
                proc.terminate()
                proc.wait(timeout=5)
        except:
            try:
                proc.kill()
            except:
                pass
        _ACTIVE_PROCESSES.discard(proc)

# Register cleanup handlers
atexit.register(_cleanup_processes)
signal.signal(signal.SIGTERM, lambda s, f: _cleanup_processes())
signal.signal(signal.SIGINT, lambda s, f: _cleanup_processes())


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
                const response = await fetch(`http://${window.location.hostname}:${port}`, {
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
                    document.getElementById('service-iframe').src = `http://${window.location.hostname}:${port}`;
                    
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
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
):
    """
    Launch the PraisonAI Unified Dashboard.
    
    Provides a single interface at localhost:3000 to access:
    - Flow Visual Builder (Langflow) - port 7860
    - Claw Dashboard (Full UI) - port 8082  
    - Clean Chat UI - port 8081
    
    This unified launcher allows you to:
    1. Create agents visually using Flow Builder
    2. Chat with agents using the Chat UI
    3. Manage everything from Claw Dashboard
    4. Connect external services like Telegram
    
    Examples:
        praisonai unified
        praisonai unified --port 9000
    """
    if ctx.invoked_subcommand is not None:
        return
    
    from rich.console import Console
    console = Console()
    
    # Check optional dependencies
    if _FASTAPI_IMPORT_ERROR:
        console.print(f"[red]Error: Missing optional dependencies for unified dashboard.[/red]")
        console.print(f"[yellow]Install with: pip install 'praisonai[api]'[/yellow]")
        console.print(f"[dim]Error details: {_FASTAPI_IMPORT_ERROR}[/dim]")
        raise typer.Abort()
    
    # Create FastAPI app
    fastapi_app = FastAPI(title="PraisonAI Unified Dashboard")
    
    @fastapi_app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return _generate_dashboard_html(host)
    
    @fastapi_app.post("/start/{service}")
    async def start_service(service: str):
        """Start a PraisonAI service."""
        if service not in SERVICE_PORTS:
            raise HTTPException(status_code=400, detail=f"Unknown service: {service}")
        
        service_port = SERVICE_PORTS[service]
        
        # Check if service is already running
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            result = sock.connect_ex(("127.0.0.1", service_port))
            if result == 0:
                sock.close()
                return {"success": True, "message": f"Service {service} already running on port {service_port}"}
        except:
            pass
        finally:
            sock.close()
        
        try:
            # Create log directory for troubleshooting
            log_dir = Path.home() / ".praisonai" / "unified" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{service}.log"
            
            if service == "flow":
                # Use proper Typer entry point for flow
                proc = subprocess.Popen([
                    sys.executable, "-m", "praisonai", "flow", 
                    "--port", str(service_port), "--no-open"
                ], stdout=open(log_file, "w"), stderr=subprocess.STDOUT)
            elif service == "claw":
                proc = subprocess.Popen([
                    sys.executable, "-m", "praisonai", "claw",
                    "--port", str(service_port)
                ], stdout=open(log_file, "w"), stderr=subprocess.STDOUT)
            elif service == "ui":
                proc = subprocess.Popen([
                    sys.executable, "-m", "praisonai", "ui",
                    "--port", str(service_port)
                ], stdout=open(log_file, "w"), stderr=subprocess.STDOUT)
            
            # Track process for cleanup
            _ACTIVE_PROCESSES.add(proc)
            
            return {"success": True, "message": f"Started {service} on port {service_port}"}
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to start {service}: {str(e)}")
    
    @fastapi_app.get("/health")
    async def health():
        return {"status": "healthy", "service": "unified-dashboard"}
    
    console.print()
    console.print("[bold green]🌟 Starting PraisonAI Unified Dashboard[/bold green]")
    console.print(f"[dim]Unified interface on {host}:{port}[/dim]")
    console.print("[dim]Access Flow Builder, Claw Dashboard, and Chat UI from one place[/dim]")
    console.print()
    
    try:
        uvicorn.run(
            fastapi_app,
            host=host,
            port=port,
            log_level="info"  # Show startup logs for debugging
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]🌟 Unified Dashboard stopped.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error starting unified dashboard: {e}[/red]")
        raise typer.Abort()
