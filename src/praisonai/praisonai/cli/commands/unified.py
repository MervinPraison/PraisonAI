"""
Unified Dashboard — launch all PraisonAI UIs from a single interface.

Usage:
    praisonai unified                 # Dashboard on :3000
    praisonai unified --port 9000     # Custom port
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = typer.Typer(help="🌟 Unified PraisonAI Interface (Flow + Claw + UI)")

UNIFIED_DIR = Path.home() / ".praisonai" / "unified"
STATIC_DIR = UNIFIED_DIR / "static"


def _ensure_static_files():
    """Create static files directory and dashboard HTML."""
    UNIFIED_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create the unified dashboard HTML
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
                const response = await fetch(`http://localhost:${port}`, {
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
            return response.ok;
        }
        
        async function openService(service, port) {
            const statusEl = document.getElementById(`${service}-status`);
            statusEl.textContent = 'Starting...';
            statusEl.className = 'status';
            
            // Try to start the service
            const started = await startService(service);
            
            if (started) {
                // Wait a moment for the service to fully start
                await new Promise(resolve => setTimeout(resolve, 3000));
                
                // Open in iframe
                document.getElementById('dashboard-view').style.display = 'none';
                document.getElementById('iframe-view').style.display = 'block';
                document.getElementById('service-iframe').src = `http://localhost:${port}`;
                
                statusEl.textContent = 'Running';
                statusEl.className = 'status running';
                activeServices[service] = port;
            } else {
                statusEl.textContent = 'Failed to Start';
                statusEl.className = 'status stopped';
                alert(`Failed to start ${service}. Check console for details.`);
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
    
    index_file = STATIC_DIR / "index.html"
    index_file.write_text(dashboard_html)
    return index_file


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
    
    # Ensure static files exist
    try:
        _ensure_static_files()
    except Exception as e:
        console.print(f"[red]Error creating static files: {e}[/red]")
        raise typer.Abort()
    
    # Create FastAPI app
    fastapi_app = FastAPI(title="PraisonAI Unified Dashboard")
    
    # Mount static files
    fastapi_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    
    @fastapi_app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return (STATIC_DIR / "index.html").read_text()
    
    @fastapi_app.post("/start/{service}")
    async def start_service(service: str):
        """Start a PraisonAI service."""
        try:
            if service == "flow":
                # Start flow in background
                subprocess.Popen([
                    sys.executable, "-m", "praisonai.cli.main", "flow", 
                    "--port", "7860", "--no-open"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif service == "claw":
                # Start claw in background
                subprocess.Popen([
                    sys.executable, "-m", "praisonai.cli.main", "claw",
                    "--port", "8082"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif service == "ui":
                # Start ui in background
                subprocess.Popen([
                    sys.executable, "-m", "praisonai.cli.main", "ui",
                    "--port", "8081"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                return {"success": False, "error": "Unknown service"}
                
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
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
            log_level="error"  # Reduce log noise
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]🌟 Unified Dashboard stopped.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error starting unified dashboard: {e}[/red]")
        raise typer.Abort()