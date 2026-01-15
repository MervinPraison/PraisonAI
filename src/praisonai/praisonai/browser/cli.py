"""Browser CLI commands for PraisonAI.

Commands:
    praisonai browser start   - Start the browser automation server
    praisonai browser stop    - Stop the server
    praisonai browser sessions - List active sessions
"""

import typer
from typing import Optional
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="browser",
    help="Browser automation commands",
    no_args_is_help=True,
)

console = Console()


@app.command("start")
def start_server(
    port: int = typer.Option(8765, "--port", "-p", help="Port to listen on"),
    host: str = typer.Option("0.0.0.0", "--host", "-H", help="Host to bind to"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="LLM model to use"),
    max_steps: int = typer.Option(20, "--max-steps", help="Maximum steps per session"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
):
    """Start the browser automation server.
    
    The server provides a WebSocket interface for the Chrome Extension
    to communicate with PraisonAI agents.
    
    Example:
        praisonai browser start --port 8765 --model gpt-4o
    """
    try:
        from praisonai.browser import BrowserServer
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("Install required dependencies: pip install fastapi uvicorn")
        raise typer.Exit(1)
    
    server = BrowserServer(
        host=host,
        port=port,
        model=model,
        max_steps=max_steps,
        verbose=verbose,
    )
    
    try:
        server.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("sessions")
def list_sessions(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum sessions to show"),
):
    """List browser automation sessions.
    
    Example:
        praisonai browser sessions --status running
        praisonai browser sessions --limit 10
    """
    try:
        from praisonai.browser.sessions import SessionManager
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    manager = SessionManager()
    sessions = manager.list_sessions(status=status, limit=limit)
    
    if not sessions:
        console.print("[dim]No sessions found[/dim]")
        return
    
    # Create table
    table = Table(title="Browser Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Goal", max_width=40)
    table.add_column("Status", style="bold")
    table.add_column("Started")
    table.add_column("URL", max_width=30)
    
    import datetime
    
    for session in sessions:
        started = datetime.datetime.fromtimestamp(session["started_at"]).strftime("%H:%M:%S")
        status_style = {
            "running": "green",
            "completed": "blue",
            "failed": "red",
            "stopped": "yellow",
        }.get(session["status"], "white")
        
        table.add_row(
            session["session_id"][:8],
            session["goal"][:40] + ("..." if len(session["goal"]) > 40 else ""),
            f"[{status_style}]{session['status']}[/{status_style}]",
            started,
            session.get("current_url", "")[:30] or "-",
        )
    
    console.print(table)
    manager.close()


@app.command("history")
def show_history(
    session_id: str = typer.Argument(..., help="Session ID to show history for"),
):
    """Show step-by-step history for a session.
    
    Example:
        praisonai browser history abc12345
    """
    try:
        from praisonai.browser.sessions import SessionManager
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    manager = SessionManager()
    
    # Find session (support partial ID)
    sessions = manager.list_sessions(limit=100)
    matched = [s for s in sessions if s["session_id"].startswith(session_id)]
    
    if not matched:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise typer.Exit(1)
    
    if len(matched) > 1:
        console.print(f"[yellow]Multiple matches:[/yellow] Please be more specific")
        for s in matched:
            console.print(f"  {s['session_id']}")
        raise typer.Exit(1)
    
    full_id = matched[0]["session_id"]
    session = manager.get_session(full_id)
    
    if not session:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise typer.Exit(1)
    
    # Print session info
    console.print(f"\n[bold]Session:[/bold] {session['session_id']}")
    console.print(f"[bold]Goal:[/bold] {session['goal']}")
    console.print(f"[bold]Status:[/bold] {session['status']}")
    console.print(f"[bold]Steps:[/bold] {len(session['steps'])}")
    
    # Print steps
    console.print("\n[bold]History:[/bold]")
    
    for step in session["steps"]:
        console.print(f"\n[cyan]Step {step['step_number']}[/cyan]")
        if step.get("action"):
            action = step["action"]
            console.print(f"  [dim]Action:[/dim] {action.get('action', 'unknown')}")
            if action.get("selector"):
                console.print(f"  [dim]Selector:[/dim] {action['selector']}")
            if action.get("text"):
                console.print(f"  [dim]Text:[/dim] {action['text']}")
            if action.get("thought"):
                console.print(f"  [dim]Thought:[/dim] {action['thought'][:100]}...")
    
    manager.close()


@app.command("clear")
def clear_sessions(
    all_sessions: bool = typer.Option(False, "--all", "-a", help="Clear all sessions"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Clear sessions with status"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Clear session history.
    
    Example:
        praisonai browser clear --status completed --yes
        praisonai browser clear --all --yes
    """
    try:
        from praisonai.browser.sessions import SessionManager
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    if not all_sessions and not status:
        console.print("[yellow]Please specify --all or --status[/yellow]")
        raise typer.Exit(1)
    
    manager = SessionManager()
    sessions = manager.list_sessions(status=status, limit=1000)
    
    if not sessions:
        console.print("[dim]No sessions to clear[/dim]")
        return
    
    if not confirm:
        if not typer.confirm(f"Delete {len(sessions)} sessions?"):
            raise typer.Abort()
    
    deleted = 0
    for session in sessions:
        if manager.delete_session(session["session_id"]):
            deleted += 1
    
    console.print(f"[green]Deleted {deleted} sessions[/green]")
    manager.close()


@app.command("run")
def run_agent(
    goal: str = typer.Argument(..., help="Goal to execute"),
    url: str = typer.Option("https://www.google.com", "--url", "-u", help="Start URL"),
    extension_path: str = typer.Option(None, "--extension", "-e", help="Extension dist path"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="LLM model"),
    max_steps: int = typer.Option(20, "--max-steps", help="Maximum steps"),
    timeout: int = typer.Option(120, "--timeout", "-t", help="Timeout in seconds"),
    headless: bool = typer.Option(False, "--headless", help="Run headless (experimental)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Debug mode - show all events"),
):
    """Run browser agent with a goal.
    
    Launches Chrome with the PraisonAI extension and executes the goal.
    
    Example:
        praisonai browser run "Search for PraisonAI on Google"
        praisonai browser run "Go to google.com and search praisonai" --url https://google.com
        praisonai browser run "task" --debug   # Shows all events
    """
    import logging
    import json
    import asyncio
    import time
    
    if verbose or debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    console.print(f"[bold blue]🚀 Starting browser agent[/bold blue]")
    console.print(f"   Goal: {goal}")
    console.print(f"   URL: {url}")
    console.print(f"   Model: {model}")
    if debug:
        console.print(f"   [dim]Debug mode: ON[/dim]")
    console.print()
    
    if debug:
        # Debug mode - connect directly to WebSocket and show all messages
        try:
            import websockets
        except ImportError:
            console.print("[red]Error:[/red] websockets required")
            raise typer.Exit(1)
        
        async def debug_run():
            port = 8765
            ws_url = f"ws://localhost:{port}/ws"
            
            try:
                async with websockets.connect(ws_url, ping_interval=30) as ws:
                    console.print("[dim]Connected to server[/dim]")
                    
                    # Send start_session
                    msg = json.dumps({"type": "start_session", "goal": goal, "model": model})
                    await ws.send(msg)
                    console.print(f"[blue]Sent:[/blue] start_session")
                    
                    start_time = time.time()
                    step_num = 0
                    
                    while time.time() - start_time < timeout:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=5)
                            data = json.loads(message)
                            msg_type = data.get("type", "unknown")
                            
                            if msg_type == "status":
                                status = data.get("status")
                                session = data.get("session_id", "")[:8]
                                console.print(f"[cyan]Status:[/cyan] {status} (session: {session})")
                                
                                if status in ("completed", "stopped", "failed"):
                                    console.print(f"[green]✅ {status.upper()}[/green]")
                                    return {"status": status, "goal": goal}
                            
                            elif msg_type == "action":
                                action = data.get("action", {})
                                action_type = action.get("action", "unknown")
                                thought = data.get("thought", "")[:80]
                                done = data.get("done", False)
                                
                                step_num += 1
                                console.print(f"\n[bold]Step {step_num}:[/bold]")
                                if thought:
                                    console.print(f"  [dim]Thought:[/dim] {thought}...")
                                console.print(f"  [yellow]Action:[/yellow] {action_type}")
                                if action.get("selector"):
                                    console.print(f"  [dim]Selector:[/dim] {action.get('selector')}")
                                if action.get("text"):
                                    console.print(f"  [dim]Text:[/dim] {action.get('text')}")
                                
                                if done:
                                    console.print(f"\n[green]✅ Task completed![/green]")
                                    return {"status": "completed", "goal": goal}
                            
                            elif msg_type == "observation":
                                url_now = data.get("url", "")[:50]
                                elements = data.get("elements", [])
                                console.print(f"[dim]Observation: {len(elements)} elements at {url_now}[/dim]")
                            
                            elif msg_type == "error":
                                error = data.get("error", "Unknown error")
                                console.print(f"[red]Error:[/red] {error}")
                                return {"status": "error", "error": error}
                            
                            else:
                                console.print(f"[dim][{msg_type}][/dim]")
                        
                        except asyncio.TimeoutError:
                            console.print("[dim].[/dim]", end="")
                            continue
                    
                    console.print(f"\n[yellow]⏱️ Timeout after {timeout}s[/yellow]")
                    return {"status": "timeout", "goal": goal}
                    
            except Exception as e:
                console.print(f"[red]Connection error:[/red] {e}")
                return {"status": "error", "error": str(e)}
        
        try:
            asyncio.run(debug_run())
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")
        return
    
    # Normal mode - poll session database for progress
    try:
        import websockets
        from praisonai.browser.sessions import SessionManager
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    async def run_with_progress():
        port = 8765
        ws_url = f"ws://localhost:{port}/ws"
        session_manager = SessionManager()
        
        try:
            async with websockets.connect(ws_url, ping_interval=30) as ws:
                # Start session
                msg = json.dumps({"type": "start_session", "goal": goal, "model": model})
                await ws.send(msg)
                
                # Wait for session_id
                session_id = None
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=10)
                    data = json.loads(message)
                    if data.get("type") == "status" and data.get("session_id"):
                        session_id = data["session_id"]
                        console.print(f"[dim]Session: {session_id[:8]}[/dim]")
                        break
                
                if not session_id:
                    console.print("[red]Failed to start session[/red]")
                    return {"status": "error"}
                
                # Poll session database for progress
                start_time = time.time()
                displayed_steps = 0
                last_url = ""
                
                console.print()
                while time.time() - start_time < timeout:
                    await asyncio.sleep(2)  # Poll every 2s
                    
                    session = session_manager.get_session(session_id)
                    if not session:
                        continue
                    
                    # Show new steps
                    for step in session["steps"][displayed_steps:]:
                        step_num = step.get("step_number", displayed_steps)
                        action = step.get("action", {})
                        thought = step.get("thought", "")[:80] if step.get("thought") else ""
                        
                        console.print(f"\n[bold]Step {step_num}:[/bold]")
                        
                        if thought:
                            console.print(f"  [dim]💭 {thought}...[/dim]")
                        
                        if action:
                            action_type = action.get("action", "wait")
                            console.print(f"  [yellow]▶ {action_type.upper()}[/yellow]", end="")
                            if action.get("selector"):
                                console.print(f" → {action.get('selector')[:40]}", end="")
                            if action.get("text"):
                                console.print(f" \"{action.get('text')}\"", end="")
                            console.print()
                        
                        displayed_steps += 1
                    
                    # Show URL changes
                    current_url = session.get("current_url", "")
                    if current_url and current_url != last_url:
                        console.print(f"  [dim]📍 {current_url[:60]}[/dim]")
                        last_url = current_url
                    
                    # Check completion
                    status = session.get("status")
                    if status == "completed":
                        console.print(f"\n[green]✅ Task completed![/green]")
                        return {"status": "completed", "session_id": session_id}
                    elif status in ("failed", "stopped"):
                        console.print(f"\n[yellow]Session {status}[/yellow]")
                        return {"status": status, "session_id": session_id}
                
                console.print(f"\n[yellow]⏱️ Timeout after {timeout}s[/yellow]")
                return {"status": "timeout", "session_id": session_id}
                
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            return {"status": "error", "error": str(e)}
        finally:
            session_manager.close()
    
    try:
        result = asyncio.run(run_with_progress())
        if result.get("session_id"):
            console.print(f"   Session: {result['session_id']}")
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        raise typer.Exit(0)


@app.command("tabs")
def manage_tabs(
    close: Optional[int] = typer.Option(None, "--close", "-c", help="Close tab by ID"),
    new: Optional[str] = typer.Option(None, "--new", "-n", help="Open new tab with URL"),
    focus: Optional[int] = typer.Option(None, "--focus", "-f", help="Focus tab by ID"),
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
):
    """List and manage browser tabs.
    
    Uses Chrome DevTools Protocol to interact with tabs.
    
    Example:
        praisonai browser tabs              # List all tabs
        praisonai browser tabs --new https://google.com
        praisonai browser tabs --close 12345
        praisonai browser tabs --focus 12345
    """
    import requests
    import json
    
    try:
        # Get tabs from Chrome DevTools Protocol
        resp = requests.get(f"http://localhost:{port}/json", timeout=5)
        targets = resp.json()
    except requests.exceptions.ConnectionError:
        console.print(f"[red]Cannot connect to Chrome on port {port}[/red]")
        console.print("[dim]Make sure Chrome is running with --remote-debugging-port[/dim]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    # Filter to just page targets
    pages = [t for t in targets if t.get("type") == "page"]
    
    # Handle actions
    if close is not None:
        # Find tab by ID (partial match)
        for page in pages:
            if str(close) in page.get("id", ""):
                try:
                    requests.get(f"http://localhost:{port}/json/close/{page['id']}", timeout=5)
                    console.print(f"[green]Closed tab:[/green] {page.get('title', 'Unknown')[:40]}")
                    return
                except Exception as e:
                    console.print(f"[red]Error closing tab:[/red] {e}")
                    raise typer.Exit(1)
        console.print(f"[yellow]Tab not found:[/yellow] {close}")
        raise typer.Exit(1)
    
    if new is not None:
        try:
            import urllib.parse
            url_encoded = urllib.parse.quote(new, safe=':/?&=')
            resp = requests.put(f"http://localhost:{port}/json/new?{new}", timeout=10)
            if resp.status_code == 200:
                new_tab = resp.json()
                console.print(f"[green]Opened new tab:[/green] {new}")
                console.print(f"   Tab ID: {new_tab.get('id', 'unknown')[:16]}")
            else:
                # Try alternative method
                resp = requests.get(f"http://localhost:{port}/json/new?{new}", timeout=10)
                new_tab = resp.json() if resp.text else {}
                console.print(f"[green]Opened new tab:[/green] {new}")
            return
        except Exception as e:
            console.print(f"[red]Error opening tab:[/red] {e}")
            raise typer.Exit(1)
    
    if focus is not None:
        for page in pages:
            if str(focus) in page.get("id", ""):
                try:
                    requests.get(f"http://localhost:{port}/json/activate/{page['id']}", timeout=5)
                    console.print(f"[green]Focused tab:[/green] {page.get('title', 'Unknown')[:40]}")
                    return
                except Exception as e:
                    console.print(f"[red]Error focusing tab:[/red] {e}")
                    raise typer.Exit(1)
        console.print(f"[yellow]Tab not found:[/yellow] {focus}")
        raise typer.Exit(1)
    
    # List tabs
    if not pages:
        console.print("[dim]No pages found[/dim]")
        return
    
    table = Table(title="Browser Tabs")
    table.add_column("#", style="dim")
    table.add_column("Title", max_width=40)
    table.add_column("URL", max_width=50)
    table.add_column("ID", style="cyan")
    
    for i, page in enumerate(pages, 1):
        title = page.get("title", "Untitled")[:40]
        url = page.get("url", "")[:50]
        tab_id = page.get("id", "")[:16]
        table.add_row(str(i), title, url, tab_id)
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(pages)} tabs[/dim]")


@app.command("navigate")
def navigate_tab(
    url: str = typer.Argument(..., help="URL to navigate to"),
    tab_id: Optional[str] = typer.Option(None, "--tab", "-t", help="Tab ID to navigate"),
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
):
    """Navigate a browser tab to a URL.
    
    Uses Chrome DevTools Protocol Page.navigate.
    
    Example:
        praisonai browser navigate "https://google.com"
        praisonai browser navigate "https://github.com" --tab ABC123
    """
    import requests
    import json
    
    try:
        import websockets
        import asyncio
    except ImportError:
        console.print("[red]Error:[/red] websockets is required")
        raise typer.Exit(1)
    
    try:
        resp = requests.get(f"http://localhost:{port}/json", timeout=5)
        targets = resp.json()
    except requests.exceptions.ConnectionError:
        console.print(f"[red]Cannot connect to Chrome on port {port}[/red]")
        raise typer.Exit(1)
    
    pages = [t for t in targets if t.get("type") == "page"]
    
    if not pages:
        console.print("[red]No pages found[/red]")
        raise typer.Exit(1)
    
    target = None
    if tab_id:
        for page in pages:
            if tab_id in page.get("id", ""):
                target = page
                break
        if not target:
            console.print(f"[yellow]Tab not found:[/yellow] {tab_id}")
            raise typer.Exit(1)
    else:
        # Use first suitable page
        for page in pages:
            page_url = page.get("url", "")
            if not page_url.startswith("chrome://") and not page_url.startswith("chrome-extension://"):
                target = page
                break
        if not target:
            target = pages[0]
    
    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        console.print("[red]No WebSocket URL for target[/red]")
        raise typer.Exit(1)
    
    async def nav():
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                if json.loads(msg).get("id") == 1:
                    break
            
            await ws.send(json.dumps({
                "id": 2,
                "method": "Page.navigate",
                "params": {"url": url}
            }))
            
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(msg)
                if data.get("id") == 2:
                    return data
    
    try:
        with console.status(f"[bold green]Navigating to {url}..."):
            result = asyncio.run(nav())
        
        if "error" in result:
            console.print(f"[red]Error:[/red] {result['error'].get('message', result['error'])}")
            raise typer.Exit(1)
        
        frame_id = result.get("result", {}).get("frameId", "")
        console.print(f"[green]✓ Navigated to:[/green] {url}")
        console.print(f"   Tab: {target.get('title', 'Unknown')[:40]}")
        
    except asyncio.TimeoutError:
        console.print("[red]Timeout during navigation[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("execute")
def execute_script(
    script: str = typer.Argument(..., help="JavaScript to execute"),
    tab_id: Optional[str] = typer.Option(None, "--tab", "-t", help="Tab ID to execute in"),
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
):
    """Execute JavaScript in a browser tab.
    
    Uses Chrome DevTools Protocol Runtime.evaluate.
    
    Example:
        praisonai browser execute "document.title"
        praisonai browser execute "window.location.href"
        praisonai browser execute "document.querySelectorAll('a').length"
    """
    import requests
    import json
    
    try:
        import websockets
        import asyncio
    except ImportError:
        console.print("[red]Error:[/red] websockets is required")
        console.print("Install: pip install websockets")
        raise typer.Exit(1)
    
    try:
        # Get tabs
        resp = requests.get(f"http://localhost:{port}/json", timeout=5)
        targets = resp.json()
    except requests.exceptions.ConnectionError:
        console.print(f"[red]Cannot connect to Chrome on port {port}[/red]")
        raise typer.Exit(1)
    
    # Find target tab
    pages = [t for t in targets if t.get("type") == "page"]
    
    if not pages:
        console.print("[red]No pages found[/red]")
        raise typer.Exit(1)
    
    target = None
    if tab_id:
        for page in pages:
            if tab_id in page.get("id", ""):
                target = page
                break
        if not target:
            console.print(f"[yellow]Tab not found:[/yellow] {tab_id}")
            raise typer.Exit(1)
    else:
        # Use first page that's not chrome:// or extension
        for page in pages:
            url = page.get("url", "")
            if not url.startswith("chrome://") and not url.startswith("chrome-extension://"):
                target = page
                break
        if not target:
            target = pages[0]
    
    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        console.print("[red]No WebSocket URL for target[/red]")
        raise typer.Exit(1)
    
    async def run_script():
        async with websockets.connect(ws_url) as ws:
            # Enable Runtime
            await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                if json.loads(msg).get("id") == 1:
                    break
            
            # Execute script
            await ws.send(json.dumps({
                "id": 2,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": True,
                    "awaitPromise": True,
                }
            }))
            
            # Get result
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(msg)
                if data.get("id") == 2:
                    return data
    
    try:
        result = asyncio.run(run_script())
        
        if "error" in result:
            console.print(f"[red]Error:[/red] {result['error'].get('message', result['error'])}")
            raise typer.Exit(1)
        
        res = result.get("result", {}).get("result", {})
        value = res.get("value")
        res_type = res.get("type", "undefined")
        
        console.print(f"[bold]Tab:[/bold] {target.get('title', 'Unknown')[:40]}")
        console.print(f"[bold]Script:[/bold] {script[:60]}")
        console.print()
        
        if res_type == "undefined":
            console.print("[dim]undefined[/dim]")
        elif res_type == "object" and value is None:
            console.print("[dim]null[/dim]")
        elif res_type == "string":
            console.print(f'[green]"{value}"[/green]')
        else:
            console.print(f"[cyan]{value}[/cyan]")
            
    except asyncio.TimeoutError:
        console.print("[red]Timeout executing script[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("screenshot")
def capture_screenshot(
    output: str = typer.Option("screenshot.png", "--output", "-o", help="Output file path"),
    tab_id: Optional[str] = typer.Option(None, "--tab", "-t", help="Tab ID to screenshot"),
    fullpage: bool = typer.Option(False, "--fullpage", "-f", help="Capture full page"),
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
):
    """Capture a screenshot of a browser tab.
    
    Uses Chrome DevTools Protocol Page.captureScreenshot.
    
    Example:
        praisonai browser screenshot
        praisonai browser screenshot -o page.png
        praisonai browser screenshot --fullpage -o full.png
    """
    import requests
    import json
    import base64
    from pathlib import Path
    
    try:
        import websockets
        import asyncio
    except ImportError:
        console.print("[red]Error:[/red] websockets is required")
        raise typer.Exit(1)
    
    try:
        resp = requests.get(f"http://localhost:{port}/json", timeout=5)
        targets = resp.json()
    except requests.exceptions.ConnectionError:
        console.print(f"[red]Cannot connect to Chrome on port {port}[/red]")
        raise typer.Exit(1)
    
    pages = [t for t in targets if t.get("type") == "page"]
    
    if not pages:
        console.print("[red]No pages found[/red]")
        raise typer.Exit(1)
    
    target = None
    if tab_id:
        for page in pages:
            if tab_id in page.get("id", ""):
                target = page
                break
        if not target:
            console.print(f"[yellow]Tab not found:[/yellow] {tab_id}")
            raise typer.Exit(1)
    else:
        for page in pages:
            page_url = page.get("url", "")
            if not page_url.startswith("chrome://") and not page_url.startswith("chrome-extension://"):
                target = page
                break
        if not target:
            target = pages[0]
    
    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        console.print("[red]No WebSocket URL for target[/red]")
        raise typer.Exit(1)
    
    async def take_screenshot():
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                if json.loads(msg).get("id") == 1:
                    break
            
            params = {"format": "png", "quality": 100}
            if fullpage:
                params["captureBeyondViewport"] = True
            
            await ws.send(json.dumps({
                "id": 2,
                "method": "Page.captureScreenshot",
                "params": params
            }))
            
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                data = json.loads(msg)
                if data.get("id") == 2:
                    return data
    
    try:
        with console.status(f"[bold green]Capturing screenshot..."):
            result = asyncio.run(take_screenshot())
        
        if "error" in result:
            console.print(f"[red]Error:[/red] {result['error'].get('message', result['error'])}")
            raise typer.Exit(1)
        
        data = result.get("result", {}).get("data", "")
        if not data:
            console.print("[red]No screenshot data received[/red]")
            raise typer.Exit(1)
        
        img_bytes = base64.b64decode(data)
        Path(output).write_bytes(img_bytes)
        
        console.print(f"[green]✓ Screenshot saved:[/green] {output}")
        console.print(f"   Tab: {target.get('title', 'Unknown')[:40]}")
        console.print(f"   Size: {len(img_bytes) // 1024} KB")
        
    except asyncio.TimeoutError:
        console.print("[red]Timeout capturing screenshot[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

