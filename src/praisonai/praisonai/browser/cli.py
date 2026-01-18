"""Browser CLI commands for PraisonAI.

Commands:
    praisonai browser start   - Start the browser automation server
    praisonai browser stop    - Stop the server
    praisonai browser sessions - List active sessions
"""

import typer
from typing import Optional
from pathlib import Path
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
    table.add_column("Steps", justify="right")
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
        
        # Get step count from manager
        steps = manager.get_step_count(session["session_id"])
        step_display = f"[green]{steps}[/green]" if steps > 0 else "[dim]0[/dim]"
        
        table.add_row(
            session["session_id"][:8],
            session["goal"][:40] + ("..." if len(session["goal"]) > 40 else ""),
            f"[{status_style}]{session['status']}[/{status_style}]",
            step_display,
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


def _run_alternative_engine(
    engine: str,
    goal: str,
    url: str,
    model: str,
    max_steps: int,
    headless: bool,
    verbose: bool,
    max_retries: int = 3,
    enable_vision: bool = False,
    screenshot_dir: Optional[str] = None,
    record_session: bool = True,
    record_video: bool = False,
    debug: bool = False,
):
    """Run browser automation using alternative engines (CDP, Playwright, or Hybrid)."""
    import asyncio
    from pathlib import Path
    from datetime import datetime
    
    console.print(f"[bold blue]🚀 Starting browser agent ({engine} mode)[/bold blue]")
    console.print(f"   Goal: {goal}")
    console.print(f"   URL: {url}")
    console.print(f"   Model: {model}")
    if enable_vision:
        console.print(f"   [cyan]Vision mode: ON[/cyan]")
    
    # Auto-create screenshot dir when record_video is enabled
    actual_screenshot_dir = screenshot_dir
    if record_video and not actual_screenshot_dir:
        actual_screenshot_dir = str(Path.home() / ".praisonai" / "browser_screenshots" / datetime.now().strftime("%Y%m%d_%H%M%S"))
        Path(actual_screenshot_dir).mkdir(parents=True, exist_ok=True)
        console.print(f"   [green]📹 Recording to: {actual_screenshot_dir}[/green]")
    elif actual_screenshot_dir:
        console.print(f"   [dim]Screenshots: {actual_screenshot_dir}[/dim]")
    console.print()
    
    async def run():
        if engine == "hybrid":
            try:
                from .cdp_agent import run_hybrid
            except ImportError as e:
                console.print(f"[red]Hybrid mode not available:[/red] {e}")
                raise typer.Exit(1)
            
            result = await run_hybrid(
                goal=goal,
                url=url,
                model=model,
                max_steps=max_steps,
                verbose=verbose,
            )
            
        elif engine == "cdp":
            try:
                from .cdp_agent import run_cdp_only
            except ImportError as e:
                console.print(f"[red]CDP agent not available:[/red] {e}")
                console.print("Install: pip install aiohttp websockets")
                raise typer.Exit(1)
            
            result = await run_cdp_only(
                goal=goal,
                url=url,
                model=model,
                max_steps=max_steps,
                verbose=verbose or debug,
                max_retries=max_retries,
                enable_vision=enable_vision or record_video,
                record_session=record_session,
                screenshot_dir=actual_screenshot_dir,
                debug=debug,
            )
            
        elif engine == "playwright":
            try:
                from .playwright_agent import run_playwright
            except ImportError as e:
                console.print(f"[red]Playwright not available:[/red] {e}")
                console.print("Install: pip install playwright && playwright install chromium")
                raise typer.Exit(1)
            
            result = await run_playwright(
                goal=goal,
                url=url,
                model=model,
                headless=headless,
                max_steps=max_steps,
                verbose=verbose,
            )
        else:
            console.print(f"[red]Unknown engine: {engine}[/red]")
            raise typer.Exit(1)
        
        # Display result
        if result.get("success"):
            console.print(f"\n[green]✅ Task completed in {result.get('steps', '?')} steps[/green]")
            if result.get("summary"):
                console.print(f"   {result['summary']}")
            console.print(f"   Final URL: {result.get('final_url', 'N/A')}")
            if result.get("engine"):
                console.print(f"   [dim]Engine used: {result['engine']}[/dim]")
            if result.get("total_retries", 0) > 0:
                console.print(f"   [dim]Retries: {result['total_retries']}[/dim]")
            if result.get("session_id"):
                console.print(f"   [dim]Session: {result['session_id'][:8]}...[/dim]")
            if result.get("screenshot"):
                console.print(f"   [dim]Screenshot saved[/dim]")
                console.print(f"   Screenshot: {result['screenshot']}")
        else:
            console.print(f"\n[red]❌ Task failed:[/red] {result.get('error', 'Unknown error')}")
            raise typer.Exit(1)
    
    asyncio.run(run())


@app.command("run")
def run_agent(
    goal: str = typer.Argument(..., help="Goal to execute"),
    url: str = typer.Option("https://www.google.com", "--url", "-u", help="Start URL"),
    extension_path: str = typer.Option(None, "--extension", "-e", help="Extension dist path"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="LLM model"),
    max_steps: int = typer.Option(20, "--max-steps", help="Maximum steps"),
    timeout: int = typer.Option(120, "--timeout", "-t", help="Timeout in seconds"),
    headless: bool = typer.Option(False, "--headless", help="Run headless (experimental)"),
    engine: str = typer.Option("extension", "--engine", help="Automation engine: extension, cdp, playwright, hybrid"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Debug mode - show all events"),
    max_retries: int = typer.Option(3, "--max-retries", help="Max retries per action on failure"),
    enable_vision: bool = typer.Option(False, "--vision", help="Enable vision-based element detection"),
    screenshot_dir: str = typer.Option(None, "--screenshots", help="Directory to save step screenshots"),
    record: bool = typer.Option(True, "--record/--no-record", help="Record session to database"),
    record_video: bool = typer.Option(False, "--record-video", help="Record video of browser session (creates GIF)"),
):
    """Run browser agent with a goal.
    
    Launches Chrome with the PraisonAI extension and executes the goal.
    
    Engines:
        extension (default): Uses Chrome extension + bridge server
        cdp: Direct Chrome DevTools Protocol (no extension needed)
        playwright: Cross-browser automation via Playwright
        hybrid: Auto-select best available engine
    
    Features:
        --max-retries: Automatic retry with alternative selectors on failures
        --vision: Enable vision-based element detection (requires gpt-4o)
        --screenshots: Save screenshots of each step for debugging
        --no-record: Disable session recording to database
    
    Example:
        praisonai browser run "Search for PraisonAI on Google"
        praisonai browser run "task" --engine cdp --headless
        praisonai browser run "task" --engine hybrid --vision
        praisonai browser run "task" --screenshots ./screenshots
    """
    import logging
    import json
    import asyncio
    import time
    
    if verbose or debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    # Handle alternative engines
    if engine in ("cdp", "playwright", "hybrid"):
        _run_alternative_engine(
            engine=engine,
            goal=goal,
            url=url,
            model=model,
            max_steps=max_steps,
            headless=headless,
            verbose=verbose,
            max_retries=max_retries,
            enable_vision=enable_vision,
            screenshot_dir=screenshot_dir,
            record_session=record,
            record_video=record_video,
            debug=debug,
        )
        return
    
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
                            
                            # Handle case where server sends non-dict data
                            if not isinstance(data, dict):
                                console.print(f"[dim]Non-dict message: {str(data)[:50]}[/dim]")
                                continue
                            
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


@app.command("pages")
def list_pages(
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all browser pages/tabs (like Antigravity's list_browser_pages).
    
    Example:
        praisonai browser pages
        praisonai browser pages --json
    """
    try:
        from .cdp_utils import get_pages_sync
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("Install: pip install aiohttp websockets")
        raise typer.Exit(1)
    
    try:
        pages = get_pages_sync(port)
    except Exception as e:
        console.print(f"[red]Failed to get pages:[/red] {e}")
        console.print("[dim]Is Chrome running with --remote-debugging-port=9222?[/dim]")
        raise typer.Exit(1)
    
    if json_output:
        import json
        console.print(json.dumps([p.to_dict() for p in pages], indent=2))
        return
    
    table = Table(title="Browser Pages")
    table.add_column("#", style="dim")
    table.add_column("Type", style="cyan", max_width=10)
    table.add_column("Title", max_width=40)
    table.add_column("URL", max_width=50)
    table.add_column("ID (use with other commands)", style="green")
    
    for i, page in enumerate(pages, 1):
        table.add_row(
            str(i),
            page.type[:10],
            page.title[:40] if page.title else "[dim]untitled[/dim]",
            page.url[:50] if page.url else "",
            page.id,
        )
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(pages)} pages[/dim]")


@app.command("dom")
def get_dom_cmd(
    page_id: str = typer.Argument(..., help="Page ID from 'pages' command"),
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
    depth: int = typer.Option(4, "--depth", "-d", help="DOM tree depth"),
):
    """Get DOM tree from a browser page (like Antigravity's browser_get_dom).
    
    Example:
        praisonai browser pages  # Get page ID
        praisonai browser dom <page-id>
    """
    import asyncio
    try:
        from .cdp_utils import get_dom
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    try:
        dom = asyncio.run(get_dom(page_id, port, depth))
    except Exception as e:
        console.print(f"[red]Failed to get DOM:[/red] {e}")
        raise typer.Exit(1)
    
    # Pretty print DOM structure
    def print_node(node, indent=0):
        name = node.get("nodeName", "")
        attrs = node.get("attributes", [])
        attr_str = ""
        if attrs:
            pairs = [f'{attrs[i]}="{attrs[i+1]}"' for i in range(0, len(attrs), 2)]
            attr_str = " " + " ".join(pairs[:3])  # Limit attributes shown
        
        if name and not name.startswith("#"):
            console.print(" " * indent + f"[cyan]<{name.lower()}{attr_str}>[/cyan]")
        
        children = node.get("children", [])
        for child in children[:10]:  # Limit children shown
            print_node(child, indent + 2)
    
    console.print("[bold]DOM Tree:[/bold]")
    print_node(dom)


@app.command("content")
def read_content(
    page_id: str = typer.Argument(..., help="Page ID from 'pages' command"),
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
    limit: int = typer.Option(2000, "--limit", "-l", help="Max characters to show"),
):
    """Read page content as text (like Antigravity's read_browser_page).
    
    Example:
        praisonai browser pages  # Get page ID
        praisonai browser content <page-id>
    """
    import asyncio
    try:
        from .cdp_utils import read_page
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    try:
        content = asyncio.run(read_page(page_id, port))
    except Exception as e:
        console.print(f"[red]Failed to read page:[/red] {e}")
        raise typer.Exit(1)
    
    console.print(f"[bold]Page Content:[/bold]\n")
    console.print(content[:limit])
    if len(content) > limit:
        console.print(f"\n[dim]... ({len(content) - limit} more characters)[/dim]")


@app.command("console")
def get_console_logs(
    page_id: str = typer.Argument(..., help="Page ID from 'pages' command"),
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
    timeout: float = typer.Option(2.0, "--timeout", "-t", help="Capture duration"),
):
    """Get console logs from a page (like Antigravity's capture_browser_console_logs).
    
    Example:
        praisonai browser pages  # Get page ID
        praisonai browser console <page-id>
    """
    import asyncio
    try:
        from .cdp_utils import get_console
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    console.print(f"[dim]Capturing console logs for {timeout}s...[/dim]")
    
    try:
        logs = asyncio.run(get_console(page_id, port, timeout))
    except Exception as e:
        console.print(f"[red]Failed to get console:[/red] {e}")
        raise typer.Exit(1)
    
    if not logs:
        console.print("[dim]No console logs captured[/dim]")
        return
    
    console.print(f"[bold]Console Logs ({len(logs)}):[/bold]\n")
    for log in logs:
        level = log.get("level", "log").upper()
        text = log.get("text", "")
        if level == "ERROR":
            console.print(f"[red][{level}][/red] {text}")
        elif level == "WARN":
            console.print(f"[yellow][{level}][/yellow] {text}")
        else:
            console.print(f"[dim][{level}][/dim] {text}")


@app.command("js")
def execute_javascript(
    page_id: str = typer.Argument(..., help="Page ID from 'pages' command"),
    code: str = typer.Argument(..., help="JavaScript code to execute"),
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
):
    """Execute JavaScript in a page (like Antigravity's execute_browser_javascript).
    
    Example:
        praisonai browser pages  # Get page ID
        praisonai browser js <page-id> "document.title"
        praisonai browser js <page-id> "document.querySelectorAll('a').length"
    """
    import asyncio
    try:
        from .cdp_utils import execute_js
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    try:
        result = asyncio.run(execute_js(page_id, code, port))
    except Exception as e:
        console.print(f"[red]JavaScript error:[/red] {e}")
        raise typer.Exit(1)
    
    console.print(f"[bold]Result:[/bold]")
    
    import json
    try:
        # Pretty print if it's JSON-serializable
        console.print(json.dumps(result, indent=2))
    except (TypeError, ValueError):
        console.print(str(result))


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


# ============================================================
# RELOAD COMMAND - Reload Chrome extension
# ============================================================

@app.command("reload")
def reload_extension(
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
):
    """Reload the PraisonAI Chrome extension.
    
    Connects to Chrome via CDP and triggers extension reload.
    Chrome must be running with --remote-debugging-port.
    
    Example:
        praisonai browser reload
    """
    import asyncio
    
    async def do_reload():
        try:
            import aiohttp
            import websockets
            import json
        except ImportError as e:
            console.print(f"[red]Missing dependencies:[/red] {e}")
            console.print("Install with: pip install aiohttp websockets")
            raise typer.Exit(1)
        
        try:
            # Get Chrome targets
            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{port}/json', timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        console.print(f"[red]Chrome not responding on port {port}[/red]")
                        raise typer.Exit(1)
                    targets = await resp.json()
            
            # Find PraisonAI extension service worker
            sw = next((t for t in targets if t.get('type') == 'service_worker' 
                       and 'praisonai' in t.get('url', '').lower()), None)
            
            if not sw:
                # Try by extension ID
                sw = next((t for t in targets if t.get('type') == 'service_worker' 
                           and 'fkmfdklcegbbpipbcimbokpfcfamhpdc' in t.get('url', '')), None)
            
            if not sw:
                console.print("[yellow]⚠️ PraisonAI extension not found[/yellow]")
                console.print("  Make sure the extension is installed and Chrome has remote debugging enabled")
                raise typer.Exit(1)
            
            console.print(f"[dim]Found extension: {sw['url'][:60]}...[/dim]")
            
            # Reload via CDP
            async with websockets.connect(sw['webSocketDebuggerUrl']) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
                await asyncio.sleep(0.5)
                await ws.send(json.dumps({
                    "id": 2,
                    "method": "Runtime.evaluate",
                    "params": {"expression": "chrome.runtime.reload()"}
                }))
            
            console.print("[green]✅ Extension reloaded successfully[/green]")
            
        except Exception as e:
            console.print(f"[red]Error reloading extension:[/red] {e}")
            raise typer.Exit(1)
    
    asyncio.run(do_reload())


# ============================================================
# CHROME MANAGEMENT COMMANDS - Start Chrome, load extension
# ============================================================

chrome_app = typer.Typer(help="Chrome browser management")
app.add_typer(chrome_app, name="chrome")


@chrome_app.command("start")
def chrome_start(
    port: int = typer.Option(9222, "--port", "-p", help="Remote debugging port"),
    headless: bool = typer.Option(False, "--headless", help="Run in headless mode"),
    profile: Optional[str] = typer.Option(None, "--profile", help="Chrome profile directory"),
    new_window: bool = typer.Option(True, "--new/--existing", help="Open new window or use existing"),
):
    """Start Chrome with remote debugging enabled.
    
    Launches Chrome with --remote-debugging-port for CDP automation.
    
    Example:
        praisonai browser chrome start              # Default port 9222
        praisonai browser chrome start -p 9333      # Custom port
        praisonai browser chrome start --headless   # Headless mode
    """
    import subprocess
    import platform
    import shutil
    
    system = platform.system()
    
    # Find Chrome executable
    if system == "Darwin":  # macOS
        chrome_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif system == "Linux":
        chrome_paths = [
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
        ]
    elif system == "Windows":
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    else:
        console.print(f"[red]Unsupported platform:[/red] {system}")
        raise typer.Exit(1)
    
    chrome_path = None
    for path in chrome_paths:
        if path and Path(path).exists():
            chrome_path = path
            break
    
    if not chrome_path:
        console.print("[red]Chrome not found.[/red] Install Google Chrome first.")
        raise typer.Exit(1)
    
    # Build command
    cmd = [chrome_path]
    cmd.append(f"--remote-debugging-port={port}")
    cmd.append("--no-first-run")
    cmd.append("--no-default-browser-check")
    
    if headless:
        cmd.append("--headless=new")
    
    if profile:
        cmd.append(f"--user-data-dir={profile}")
    
    if new_window:
        cmd.append("--new-window")
    
    # Check if Chrome is already listening on this port
    import asyncio
    
    async def check_port():
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{port}/json/version", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        return True
        except Exception:
            pass
        return False
    
    if asyncio.run(check_port()):
        console.print(f"[green]Chrome is already running with debug port {port}[/green]")
        return
    
    console.print(f"[cyan]Starting Chrome on port {port}...[/cyan]")
    console.print(f"[dim]{' '.join(cmd[:3])}...[/dim]")
    
    try:
        # Start Chrome in background
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        
        # Wait and verify CDP is working
        import time
        max_attempts = 5
        for attempt in range(max_attempts):
            time.sleep(1)
            if asyncio.run(check_port()):
                console.print(f"[green]✓ Chrome started successfully[/green]")
                console.print(f"  Debug URL: http://localhost:{port}")
                console.print(f"  PID: {process.pid}")
                console.print("")
                console.print("[dim]Next steps:[/dim]")
                console.print(f"  praisonai browser chrome status -p {port}")
                console.print(f"  praisonai browser extension load -p {port}")
                return
        
        # Chrome didn't respond - check if it's still running but on wrong port
        if process.poll() is not None:
            stderr = process.stderr.read().decode() if process.stderr else ""
            console.print("[yellow]Chrome exited immediately.[/yellow]")
            console.print("This usually means Chrome is already running.")
            if "already running" in stderr.lower() or stderr:
                console.print(f"[dim]{stderr[:200]}[/dim]")
            console.print("")
            console.print("[bold]To fix:[/bold]")
            console.print("  1. Close all Chrome windows completely")
            console.print("  2. Or restart Chrome with debug port manually:")
            console.print(f"     /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port={port} &")
        else:
            console.print("[yellow]Chrome started but CDP not responding.[/yellow]")
            console.print("The debug port may be blocked or Chrome crashed.")
            
        raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]Error starting Chrome:[/red] {e}")
        raise typer.Exit(1)


@chrome_app.command("status")
def chrome_status(
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
):
    """Check if Chrome is running with debug port.
    
    Example:
        praisonai browser chrome status
        praisonai browser chrome status -p 9333
    """
    import asyncio
    
    async def check():
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{port}/json/version", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        console.print(f"[green]✓ Chrome is running on port {port}[/green]")
                        console.print(f"  Browser: {data.get('Browser', 'Unknown')}")
                        console.print(f"  V8: {data.get('V8-Version', 'Unknown')[:20]}")
                        return True
        except Exception:
            pass
        
        console.print(f"[red]✗ Chrome not responding on port {port}[/red]")
        console.print(f"  Start with: praisonai browser chrome start -p {port}")
        return False
    
    asyncio.run(check())


@chrome_app.command("stop")
def chrome_stop(
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
):
    """Stop Chrome browser via CDP.
    
    Example:
        praisonai browser chrome stop
    """
    import asyncio
    
    async def stop():
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{port}/json/close", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        console.print(f"[green]Chrome stopped[/green]")
                        return
        except Exception:
            pass
        
        console.print(f"[yellow]Could not stop Chrome on port {port}[/yellow]")
        console.print("Chrome may not be running or may need manual termination.")
    
    asyncio.run(stop())


# Extension management commands
extension_app = typer.Typer(help="Chrome extension management")
app.add_typer(extension_app, name="extension")


@extension_app.command("load")
def extension_load(
    path: Optional[str] = typer.Argument(None, help="Extension directory path"),
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Validate manifest before loading"),
):
    """Load PraisonAI extension into Chrome.
    
    Validates the manifest and provides instructions for loading.
    Chrome doesn't support programmatic extension loading, so this
    command validates and opens chrome://extensions for manual loading.
    
    Example:
        praisonai browser extension load              # Default path
        praisonai browser extension load ~/my-ext     # Custom path
    """
    from pathlib import Path
    import json
    import webbrowser
    import asyncio
    
    # Default extension path
    if path is None:
        path = str(Path.home() / "praisonai-chrome-extension" / "dist")
    
    ext_path = Path(path)
    
    # Check if path exists
    if not ext_path.exists():
        console.print(f"[red]Extension path not found:[/red] {ext_path}")
        console.print("")
        console.print("Expected location: ~/praisonai-chrome-extension/dist")
        console.print("Build the extension first:")
        console.print("  cd ~/praisonai-chrome-extension && npm run build")
        raise typer.Exit(1)
    
    # Check for manifest.json
    manifest_path = ext_path / "manifest.json"
    if not manifest_path.exists():
        console.print(f"[red]manifest.json not found in:[/red] {ext_path}")
        raise typer.Exit(1)
    
    # Validate manifest if requested
    if validate:
        errors = _validate_manifest(manifest_path)
        if errors:
            console.print("[red]Manifest validation errors:[/red]")
            for error in errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)
        console.print("[green]✓ Manifest is valid[/green]")
    
    # Check Chrome status
    async def check_chrome():
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{port}/json/version", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    return resp.status == 200
        except Exception:
            return False
    
    chrome_running = asyncio.run(check_chrome())
    
    if not chrome_running:
        console.print(f"[yellow]Chrome not running on port {port}[/yellow]")
        console.print(f"Start Chrome first: praisonai browser chrome start -p {port}")
        raise typer.Exit(1)
    
    # Open chrome://extensions
    console.print("")
    console.print(f"[cyan]Extension ready to load:[/cyan] {ext_path}")
    console.print("")
    console.print("[bold]To load the extension:[/bold]")
    console.print("  1. Go to chrome://extensions")
    console.print("  2. Enable 'Developer mode' (top right)")
    console.print("  3. Click 'Load unpacked'")
    console.print(f"  4. Select: {ext_path}")
    console.print("")
    
    open_browser = typer.confirm("Open chrome://extensions now?", default=True)
    if open_browser:
        webbrowser.open("chrome://extensions")
        console.print("[green]Opened chrome://extensions[/green]")


@extension_app.command("validate")
def extension_validate(
    path: Optional[str] = typer.Argument(None, help="Extension directory path"),
):
    """Validate Chrome extension manifest.
    
    Checks for common manifest errors before loading.
    
    Example:
        praisonai browser extension validate
        praisonai browser extension validate ~/my-ext/dist
    """
    from pathlib import Path
    
    # Default extension path
    if path is None:
        path = str(Path.home() / "praisonai-chrome-extension" / "dist")
    
    ext_path = Path(path)
    manifest_path = ext_path / "manifest.json"
    
    if not manifest_path.exists():
        # Try parent directory
        manifest_path = ext_path / "manifest.json"
        if not manifest_path.exists():
            console.print(f"[red]manifest.json not found in:[/red] {ext_path}")
            raise typer.Exit(1)
    
    errors = _validate_manifest(manifest_path)
    
    if errors:
        console.print("[red]Validation failed:[/red]")
        for error in errors:
            console.print(f"  ✗ {error}")
        raise typer.Exit(1)
    else:
        console.print("[green]✓ Manifest is valid[/green]")
        console.print(f"  Path: {manifest_path}")


def _validate_manifest(manifest_path: Path) -> list:
    """Validate Chrome extension manifest.json and return list of errors."""
    import json
    
    errors = []
    
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]
    
    # Required fields
    required = ["manifest_version", "name", "version"]
    for field in required:
        if field not in manifest:
            errors.append(f"Missing required field: {field}")
    
    # Manifest version
    if manifest.get("manifest_version") not in [2, 3]:
        errors.append(f"Invalid manifest_version: {manifest.get('manifest_version')}")
    
    # Commands validation (the problematic area)
    commands = manifest.get("commands", {})
    valid_modifiers = {"Ctrl", "Alt", "Shift", "Command", "MacCtrl"}
    
    for cmd_name, cmd_data in commands.items():
        if "suggested_key" in cmd_data:
            suggested = cmd_data["suggested_key"]
            
            # Check mac key format
            if "mac" in suggested:
                mac_key = suggested["mac"]
                # Chrome MV3 uses Command/Option/etc, not Option alone with certain keys
                # Option+S specifically can cause issues
                if "Option+" in mac_key:
                    key = mac_key.split("+")[-1]
                    if key.upper() in ["S", "N", "T", "W"]:  # Reserved keys
                        errors.append(f"commands.{cmd_name}.mac: '{mac_key}' may conflict with Chrome shortcuts. Use Command+Shift+{key} instead.")
            
            # Check default key format
            if "default" in suggested:
                default_key = suggested["default"]
                parts = default_key.split("+")
                if len(parts) < 2:
                    errors.append(f"commands.{cmd_name}.default: invalid format '{default_key}'")
    
    # Check for service_worker in MV3
    if manifest.get("manifest_version") == 3:
        background = manifest.get("background", {})
        if "scripts" in background:
            errors.append("MV3 requires 'service_worker' in background, not 'scripts'")
    
    return errors


# ============================================================
# DOCTOR COMMAND GROUP - Health diagnostics
# ============================================================

doctor_app = typer.Typer(help="Browser health diagnostics")
app.add_typer(doctor_app, name="doctor")


@doctor_app.command("server")
def doctor_server(
    host: str = typer.Option("localhost", "--host", "-H", help="Server host"),
    port: int = typer.Option(8765, "--port", "-p", help="Server port"),
):
    """Check bridge server status."""
    import requests
    
    try:
        resp = requests.get(f"http://{host}:{port}/health", timeout=5)
        data = resp.json()
        console.print(f"[green]✅ Server: {data['status']}[/green]")
        console.print(f"   Connections: {data.get('connections', 0)}")
        console.print(f"   Sessions: {data.get('sessions', 0)}")
    except requests.exceptions.ConnectionError:
        console.print(f"[red]❌ Server not running on {host}:{port}[/red]")
        console.print("   Start with: praisonai browser start")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Server error:[/red] {e}")
        raise typer.Exit(1)


@doctor_app.command("chrome")
def doctor_chrome(
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
):
    """Check Chrome remote debugging."""
    import requests
    
    try:
        resp = requests.get(f"http://localhost:{port}/json/version", timeout=5)
        data = resp.json()
        console.print(f"[green]✅ Chrome: {data.get('Browser', 'Unknown')}[/green]")
        console.print(f"   WebSocket: {data.get('webSocketDebuggerUrl', 'N/A')[:50]}...")
    except requests.exceptions.ConnectionError:
        console.print(f"[red]❌ Chrome not running with --remote-debugging-port={port}[/red]")
        console.print("   Start Chrome with:")
        console.print(f'   google-chrome --remote-debugging-port={port}')
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Chrome error:[/red] {e}")
        raise typer.Exit(1)


@doctor_app.command("extension")
def doctor_extension(
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
):
    """Check PraisonAI extension status."""
    import requests
    
    try:
        resp = requests.get(f"http://localhost:{port}/json", timeout=5)
        targets = resp.json()
        
        # Find extension service worker
        sw = next((t for t in targets if t.get('type') == 'service_worker' 
                   and ('praisonai' in t.get('url', '').lower() or 
                        'fkmfdklcegbbpipbcimbokpfcfamhpdc' in t.get('url', ''))), None)
        
        if sw:
            console.print("[green]✅ Extension loaded[/green]")
            console.print(f"   URL: {sw['url'][:60]}...")
            console.print(f"   Status: {sw.get('type', 'unknown')}")
        else:
            console.print("[yellow]⚠️ Extension not found[/yellow]")
            console.print("   Install from: chrome://extensions (load unpacked)")
            
    except requests.exceptions.ConnectionError:
        console.print(f"[red]❌ Cannot connect to Chrome on port {port}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Error checking extension:[/red] {e}")
        raise typer.Exit(1)


@doctor_app.command("test-extension")
def doctor_test_extension(
    goal: str = typer.Option("Go to google.com and confirm the page loaded", "--goal", "-g", help="Test goal to execute"),
    url: str = typer.Option("https://www.google.com", "--url", "-u", help="Starting URL"),
    timeout: int = typer.Option(60, "--timeout", "-t", help="Timeout in seconds"),
    debug: bool = typer.Option(True, "--debug/--no-debug", help="Enable debug output"),
):
    """Test extension mode end-to-end.
    
    This command verifies that extension mode works:
    1. Check if bridge server is running
    2. Send a test goal via WebSocket
    3. Report success/failure with diagnostics
    
    Examples:
        praisonai browser doctor test-extension
        praisonai browser doctor test-extension --goal "Search for AI"
        praisonai browser doctor test-extension --timeout 30
    """
    import asyncio
    from rich.table import Table
    
    console.print("[bold]Extension Mode Test[/bold]\n")
    
    async def run_test():
        from .server import test_extension_mode
        return await test_extension_mode(
            goal=goal,
            url=url,
            debug=debug,
            timeout=float(timeout),
        )
    
    try:
        result = asyncio.run(run_test())
        
        # Display diagnostics
        console.print("[dim]Diagnostics:[/dim]")
        for diag in result.get("diagnostics", []):
            console.print(f"  {diag}")
        console.print()
        
        # Summary table
        table = Table(show_header=False)
        table.add_column("Check", style="cyan")
        table.add_column("Status")
        
        table.add_row("Bridge Server", "✅ Running" if result.get("bridge_server_running") else "❌ Not running")
        table.add_row("Goal Executed", "✅ Yes" if result.get("goal_executed") else "❌ No")
        table.add_row("Success", "✅ Yes" if result.get("success") else "❌ No")
        
        if result.get("steps"):
            table.add_row("Steps", str(result.get("steps")))
        
        console.print(table)
        
        if result.get("error"):
            console.print(f"\n[red]Error:[/red] {result['error']}")
        
        if result.get("summary"):
            console.print(f"\n[green]Summary:[/green] {result['summary']}")
        
        if result.get("success"):
            console.print("\n[green]✅ Extension mode is working![/green]")
        else:
            console.print("\n[yellow]⚠️ Extension mode test failed[/yellow]")
            console.print("Make sure:")
            console.print("  1. Bridge server is running: praisonai browser start")
            console.print("  2. Chrome extension is loaded")
            console.print("  3. Side panel is open in Chrome")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]❌ Test failed:[/red] {e}")
        raise typer.Exit(1)


@doctor_app.command("db")
def doctor_db():
    """Check session database status."""
    from pathlib import Path
    import sqlite3
    
    db_path = Path.home() / ".praisonai" / "browser_sessions.db"
    
    if not db_path.exists():
        console.print("[yellow]⚠️ Session database not found[/yellow]")
        console.print(f"   Expected: {db_path}")
        console.print("   Will be created on first session")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM sessions")
        session_count = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM steps")
        step_count = c.fetchone()[0]
        
        c.execute("SELECT status, COUNT(*) FROM sessions GROUP BY status")
        status_counts = dict(c.fetchall())
        
        conn.close()
        
        console.print(f"[green]✅ Session database[/green]")
        console.print(f"   Path: {db_path}")
        console.print(f"   Sessions: {session_count}")
        console.print(f"   Steps: {step_count}")
        for status, count in status_counts.items():
            console.print(f"   - {status}: {count}")
            
    except Exception as e:
        console.print(f"[red]❌ Database error:[/red] {e}")
        raise typer.Exit(1)


@doctor_app.command("bridge")
def doctor_bridge(
    host: str = typer.Option("localhost", "--host", "-H", help="Server host"),
    port: int = typer.Option(8765, "--port", "-p", help="Server port"),
):
    """Test bridge WebSocket connectivity.
    
    Performs:
    1. HTTP health check
    2. WebSocket handshake test
    3. Welcome message validation
    
    Examples:
        praisonai browser doctor bridge
        praisonai browser doctor bridge --port 8766
    """
    import asyncio
    from .diagnostics import check_bridge_server, check_bridge_websocket
    
    console.print("[bold]Bridge Server Test[/bold]\n")
    
    async def run_checks():
        results = []
        results.append(await check_bridge_server(host, port))
        results.append(await check_bridge_websocket(host, port))
        return results
    
    results = asyncio.run(run_checks())
    
    all_pass = True
    for r in results:
        if r.status.value == "pass":
            console.print(f"[green]✅ {r.name}:[/green] {r.message}")
        elif r.status.value == "fail":
            console.print(f"[red]❌ {r.name}:[/red] {r.message}")
            all_pass = False
        else:
            console.print(f"[yellow]⚠️ {r.name}:[/yellow] {r.message}")
        
        if r.details:
            for k, v in r.details.items():
                console.print(f"   {k}: {v}")
    
    if not all_pass:
        raise typer.Exit(1)


@doctor_app.command("api-keys")
def doctor_api_keys(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Test specific model API"),
    validate: bool = typer.Option(False, "--validate", "-V", help="Actually call API to validate key"),
):
    """Check API key configuration.
    
    Verifies:
    - OPENAI_API_KEY
    - GEMINI_API_KEY
    - ANTHROPIC_API_KEY
    
    Examples:
        praisonai browser doctor api-keys
        praisonai browser doctor api-keys --validate
        praisonai browser doctor api-keys --model gemini/gemini-2.0-flash --validate
    """
    from .diagnostics import check_api_keys, check_api_key_valid
    
    console.print("[bold]API Key Check[/bold]\n")
    
    results = check_api_keys()
    
    all_pass = True
    for r in results:
        provider = r.details.get('provider', r.name)
        if r.status.value == "pass":
            console.print(f"[green]✅ {provider}:[/green] {r.message}")
        elif r.status.value == "fail":
            console.print(f"[red]❌ {provider}:[/red] {r.message}")
            all_pass = False
        else:
            console.print(f"[yellow]⚠️ {provider}:[/yellow] {r.message}")

    
    # Validate with actual API call
    if validate:
        console.print("\n[dim]Validating with API call...[/dim]")
        test_model = model or "gpt-4o-mini"
        result = check_api_key_valid(test_model)
        
        if result.status.value == "pass":
            console.print(f"[green]✅ API validation:[/green] {result.message}")
        else:
            console.print(f"[red]❌ API validation:[/red] {result.message}")
            if result.details.get("error"):
                console.print(f"   Error: {result.details['error'][:100]}")
            all_pass = False
    
    if not all_pass:
        raise typer.Exit(1)


@doctor_app.command("env")
def doctor_env():
    """Show environment configuration.
    
    Displays:
    - Python version
    - Platform
    - API key status
    - Working directory
    
    Examples:
        praisonai browser doctor env
    """
    from .diagnostics import get_environment_info
    
    console.print("[bold]Environment Configuration[/bold]\n")
    
    result = get_environment_info()
    details = result.details
    
    console.print(f"Python: {details.get('python_version', 'unknown')}")
    console.print(f"Platform: {details.get('platform', 'unknown')}")
    console.print(f"Home: {details.get('home', 'unknown')}")
    console.print(f"CWD: {details.get('cwd', 'unknown')}")
    
    console.print("\n[bold]API Keys:[/bold]")
    api_keys = details.get("api_keys_set", {})
    for key, is_set in api_keys.items():
        if key == "OPENAI_BASE_URL":
            console.print(f"  {key}: {is_set}")
        elif is_set:
            console.print(f"  [green]✅ {key}[/green]: Set")
        else:
            console.print(f"  [yellow]⚠️ {key}[/yellow]: Not set")


@doctor_app.command("agent")
def doctor_agent(
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="LLM model to test"),
):
    """Test agent LLM capability.
    
    Sends a mock observation and verifies agent returns valid action.
    This tests the full LLM call path.
    
    Examples:
        praisonai browser doctor agent
        praisonai browser doctor agent --model gemini/gemini-2.0-flash
    """
    import asyncio
    from .diagnostics import check_agent_llm, check_vision_capability
    
    console.print(f"[bold]Agent LLM Test ({model})[/bold]\n")
    
    # Check vision capability
    vision_result = check_vision_capability(model)
    if vision_result.status.value == "pass":
        console.print(f"[green]✅ Vision:[/green] {vision_result.message}")
    else:
        console.print(f"[yellow]⚠️ Vision:[/yellow] {vision_result.message}")
    
    # Test LLM call
    console.print("\n[dim]Testing LLM call...[/dim]")
    result = asyncio.run(check_agent_llm(model))
    
    if result.status.value == "pass":
        console.print(f"[green]✅ Agent:[/green] {result.message}")
        if result.details.get("thought"):
            console.print(f"   Thought: {result.details['thought'][:80]}...")
    elif result.status.value == "fail":
        console.print(f"[red]❌ Agent:[/red] {result.message}")
        if result.details.get("error"):
            console.print(f"   Error: {result.details['error'][:150]}")
        raise typer.Exit(1)
    else:
        console.print(f"[yellow]⚠️ Agent:[/yellow] {result.message}")


@doctor_app.command("flow")
def doctor_flow(
    bridge_port: int = typer.Option(8765, "--bridge-port", help="Bridge server port"),
    chrome_port: int = typer.Option(9222, "--chrome-port", help="Chrome debug port"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="LLM model"),
    skip_llm: bool = typer.Option(False, "--skip-llm", help="Skip LLM API test"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Run full automation flow diagnostics.
    
    Tests all components in sequence:
    1. Environment & API keys
    2. Bridge server connectivity
    3. Chrome CDP & extension
    4. Agent LLM capability
    
    Examples:
        praisonai browser doctor flow
        praisonai browser doctor flow --json
        praisonai browser doctor flow --skip-llm
    """
    import asyncio
    import json as json_lib
    from .diagnostics import run_all_diagnostics
    
    if not json_output:
        console.print("[bold]Full Automation Flow Diagnostics[/bold]\n")
    
    results = asyncio.run(run_all_diagnostics(
        bridge_port=bridge_port,
        chrome_port=chrome_port,
        model=model,
        skip_llm=skip_llm,
    ))
    
    if json_output:
        console.print(json_lib.dumps(results, indent=2))
        return
    
    # Display results
    for r in results["results"]:
        status = r["status"]
        name = r["name"]
        message = r["message"]
        
        if status == "pass":
            console.print(f"[green]✅ {name}:[/green] {message}")
        elif status == "fail":
            console.print(f"[red]❌ {name}:[/red] {message}")
        elif status == "warn":
            console.print(f"[yellow]⚠️ {name}:[/yellow] {message}")
        else:
            console.print(f"[dim]⏭️ {name}:[/dim] {message}")
    
    # Summary
    summary = results["summary"]
    console.print(f"\n[bold]Summary:[/bold] {summary['passed']}/{summary['total']} passed")
    
    if summary["failed"] > 0:
        console.print(f"[red]  ❌ {summary['failed']} failed[/red]")
    if summary["warned"] > 0:
        console.print(f"[yellow]  ⚠️ {summary['warned']} warnings[/yellow]")
    
    if not summary["all_pass"]:
        raise typer.Exit(1)


@doctor_app.callback(invoke_without_command=True)
def doctor_all(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Run all browser health checks.
    
    Runs comprehensive diagnostics on all components.
    
    Examples:
        praisonai browser doctor
        praisonai browser doctor --json
    """
    if ctx.invoked_subcommand is None:
        # Use full flow diagnostics
        doctor_flow(
            bridge_port=8765,
            chrome_port=9222,
            model="gpt-4o-mini",
            skip_llm=True,  # Skip by default for speed
            json_output=json_output,
        )


# ============================================================
# LAUNCH COMMAND - All-in-one browser automation setup
# ============================================================

@app.command("launch")
def launch_browser(
    goal: Optional[str] = typer.Argument(None, help="Goal to execute (optional)"),
    url: str = typer.Option("https://www.google.com", "--url", "-u", help="Start URL"),
    extension_path: Optional[str] = typer.Option(None, "--extension", "-e", help="Extension dist path"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="LLM model"),
    max_steps: int = typer.Option(20, "--max-steps", help="Maximum steps"),
    timeout: float = typer.Option(120.0, "--timeout", "-t", help="Timeout in seconds for automation"),
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debug port"),
    server_port: int = typer.Option(8765, "--server-port", help="Bridge server port"),
    headless: bool = typer.Option(False, "--headless", help="Run headless"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Debug mode with detailed logging"),
    no_server: bool = typer.Option(False, "--no-server", help="Don't start bridge server"),
    record_video: bool = typer.Option(False, "--record-video", help="Record video of browser session"),
    screenshot: bool = typer.Option(False, "--screenshot", help="Capture screenshots per step"),
    log_file: Optional[str] = typer.Option(None, "--log-file", help="Save debug logs to file (auto-generated if --debug without path)"),
    engine: str = typer.Option("auto", "--engine", help="Automation engine: extension, cdp, auto (default: auto)"),
    profile: bool = typer.Option(False, "--profile", help="Enable performance profiling with timing summary"),
    deep_profile: bool = typer.Option(False, "--deep-profile", help="Enable deep profiling with cProfile trace"),
    no_verify: bool = typer.Option(False, "--no-verify", help="Disable action verification (faster but less reliable)"),
    temp_profile: bool = typer.Option(False, "--temp-profile", help="Use temporary profile (deleted after run). Default: ~/.praisonai/browser_profile"),
    chrome_profile: Optional[str] = typer.Option(None, "--chrome-profile", help="Custom Chrome profile dir. Default: ~/.praisonai/browser_profile"),
):
    """Launch Chrome with extension and optionally run a goal.
    
    This is an all-in-one command that:
    1. Finds the PraisonAI Chrome extension
    2. Starts the bridge server (unless --no-server)
    3. Launches Chrome with the extension loaded via --load-extension
    4. Runs browser automation goal using the extension (or CDP as fallback)
    
    Engine modes:
        extension: Use Chrome extension via bridge server (recommended)
        cdp:       Direct Chrome DevTools Protocol (no extension)
        auto:      Try extension first, fall back to CDP if unavailable
    
    The extension provides better reliability, visual feedback, and
    enhanced element detection compared to pure CDP mode.
    
    Examples:
        praisonai browser launch                           # Just launch Chrome with extension
        praisonai browser launch "Search for AI"           # Launch and run goal (uses extension)
        praisonai browser launch "Search" --engine cdp     # Force CDP mode
        praisonai browser launch "Search" --engine extension  # Force extension mode
        praisonai browser launch --headless --no-server    # Headless mode, no server
    """
    import subprocess
    import platform
    import shutil
    import tempfile
    import time
    import asyncio
    import os
    import logging
    from pathlib import Path
    from datetime import datetime
    
    # Setup logging for debug mode
    log_dir = Path.home() / ".praisonai" / "browser_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup screenshot directory if enabled
    screenshot_dir = None
    if screenshot or debug:
        screenshot_dir = Path.home() / ".praisonai" / "browser_screenshots" / datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup log file
    actual_log_file = None
    if debug:
        if log_file:
            actual_log_file = Path(log_file)
        else:
            actual_log_file = log_dir / f"launch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # Configure clean, user-friendly logging
        # Use Rich handler for colored console output
        from rich.logging import RichHandler
        
        # File handler for full debug logs (includes all details)
        file_handler = logging.FileHandler(actual_log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        
        # Rich console handler for clean, readable output
        console_handler = RichHandler(
            rich_tracebacks=True,
            show_time=False,  # Cleaner output
            show_path=False,  # Hide file paths
            markup=True,
        )
        console_handler.setLevel(logging.DEBUG)
        
        logging.basicConfig(
            level=logging.DEBUG,
            handlers=[file_handler, console_handler],
        )
        
        # ===== NOISE FILTERING =====
        # Silence noisy third-party loggers (they flood the output)
        logging.getLogger("websockets").setLevel(logging.WARNING)
        logging.getLogger("websockets.client").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        
        # ===== PRAISONAI BROWSER LOGS =====
        # Enable DEBUG only for PraisonAI browser components
        logging.getLogger("praisonai.browser").setLevel(logging.DEBUG)
        logging.getLogger("praisonai.browser.server").setLevel(logging.DEBUG)
        logging.getLogger("praisonai.browser.agent").setLevel(logging.DEBUG)
        logging.getLogger("praisonai.browser.sessions").setLevel(logging.DEBUG)
        logging.getLogger("praisonai.browser.cdp_agent").setLevel(logging.DEBUG)
        logging.getLogger("praisonai.browser.diagnostics").setLevel(logging.DEBUG)
        
        console.print(f"[cyan]Debug logging enabled[/cyan]")
        console.print(f"   Log file: {actual_log_file}")
        console.print(f"   [dim]Full websocket logs saved to file only[/dim]")
        if screenshot_dir:
            console.print(f"   Screenshots: {screenshot_dir}")
        console.print()

    
    # Find Chrome executable
    system = platform.system()
    chrome_path = None
    
    if system == "Darwin":  # macOS
        # Chrome 137+ removed --load-extension for branded Chrome
        # Prioritize Chrome for Testing which still supports it
        home = os.path.expanduser("~")
        candidates = [
            # Chrome for Testing (supports --load-extension in Chrome 137+)
            os.path.join(home, ".praisonai/chrome-for-testing/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
            os.path.join(home, ".praisonai/chrome-for-testing/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
            # Chromium also supports --load-extension
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            # Fallback to branded Chrome (--load-extension may not work on 137+)
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        ]
    elif system == "Windows":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
    else:  # Linux
        candidates = [
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
        ]
    
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            chrome_path = candidate
            break
    
    if not chrome_path:
        console.print("[red]Chrome not found.[/red] Install Google Chrome first.")
        raise typer.Exit(1)
    
    # Find extension path
    if extension_path is None:
        ext_candidates = [
            Path.home() / "praisonai-chrome-extension" / "dist",
            Path.cwd() / "praisonai-chrome-extension" / "dist",
            Path(__file__).parent.parent.parent.parent.parent / "praisonai-chrome-extension" / "dist",
        ]
        for candidate in ext_candidates:
            if candidate.exists() and (candidate / "manifest.json").exists():
                extension_path = str(candidate)
                break
    
    if not extension_path or not Path(extension_path).exists():
        console.print("[red]Extension not found.[/red]")
        console.print("Expected location: ~/praisonai-chrome-extension/dist")
        console.print("Build the extension first:")
        console.print("  cd ~/praisonai-chrome-extension && npm run build")
        raise typer.Exit(1)
    
    console.print(f"[bold blue]🚀 PraisonAI Browser Launch[/bold blue]")
    console.print(f"   Chrome: {chrome_path[:50]}...")
    console.print(f"   Extension: {extension_path}")
    if goal:
        console.print(f"   Goal: {goal}")
    console.print()
    
    # =========================================================================
    # PRE-FLIGHT CHECK: Validate API key for the selected model
    # =========================================================================
    model_lower = model.lower()
    api_key_warning = None
    
    if "gemini" in model_lower:
        if not os.environ.get("GEMINI_API_KEY"):
            api_key_warning = "GEMINI_API_KEY"
    elif "gpt" in model_lower or "openai" in model_lower:
        if not os.environ.get("OPENAI_API_KEY"):
            api_key_warning = "OPENAI_API_KEY"
    elif "claude" in model_lower or "anthropic" in model_lower:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            api_key_warning = "ANTHROPIC_API_KEY"
    
    if api_key_warning:
        console.print(f"[bold red]⚠️  WARNING: {api_key_warning} is not set![/bold red]")
        console.print(f"[red]   Model '{model}' requires this API key to work.[/red]")
        console.print(f"[yellow]   Set it with: export {api_key_warning}=\"your-key-here\"[/yellow]")
        console.print()
        # Give user a chance to see the warning
        time.sleep(1)
    
    # Start bridge server if needed
    server_process = None
    if not no_server:
        # Check if server is already running
        async def check_server():
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://localhost:{server_port}/health", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                        return resp.status == 200
            except Exception:
                return False
        
        server_running = asyncio.run(check_server())
        
        if not server_running:
            console.print(f"[cyan]Starting bridge server on port {server_port}...[/cyan]")
            # Start server in background
            import sys
            server_process = subprocess.Popen(
                [sys.executable, "-m", "praisonai.browser.server", "--port", str(server_port)],
                stdout=subprocess.PIPE if not verbose else None,
                stderr=subprocess.PIPE if not verbose else None,
                start_new_session=True,
            )
            time.sleep(2)  # Give server time to start
            
            # Verify server started
            if asyncio.run(check_server()):
                console.print(f"[green]✓ Bridge server started[/green]")
            else:
                console.print("[yellow]⚠️ Bridge server may not have started properly[/yellow]")
        else:
            console.print(f"[green]✓ Bridge server already running on port {server_port}[/green]")
    
    # Default persistent profile path
    DEFAULT_PROFILE_PATH = os.path.expanduser("~/.praisonai/browser_profile")
    
    # Determine profile to use: --temp-profile = temp, else persistent (default or custom)
    if temp_profile:
        # Use temp profile (deleted after run)
        profile_dir = tempfile.mkdtemp(prefix="praisonai_chrome_")
        using_persistent_profile = False
        if debug:
            console.print(f"[dim]Using temp profile: {profile_dir}[/dim]")
    else:
        # Use persistent profile (default or custom)
        profile_dir = chrome_profile or DEFAULT_PROFILE_PATH
        os.makedirs(profile_dir, exist_ok=True)
        using_persistent_profile = True
        console.print(f"[cyan]Using persistent Chrome profile: {profile_dir}[/cyan]")
    
    # Build Chrome command with --load-extension
    chrome_args = [
        chrome_path,
        f"--load-extension={extension_path}",
        f"--disable-extensions-except={extension_path}",  # Critical: only load our extension
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={port}",
        "--enable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "--disable-popup-blocking",
        "--disable-translate",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-device-discovery-notifications",
        url,
    ]
    
    if headless:
        chrome_args.insert(1, "--headless=new")
    
    console.print(f"[cyan]Launching Chrome with extension...[/cyan]")
    if debug:
        console.print(f"[dim]{' '.join(chrome_args[:5])}...[/dim]")
    
    chrome_process = subprocess.Popen(
        chrome_args,
        stdout=subprocess.PIPE if not verbose else None,
        stderr=subprocess.PIPE if not verbose else None,
    )
    
    # Wait for Chrome to start
    time.sleep(3)
    
    # Verify Chrome is running with CDP
    async def check_chrome():
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{port}/json/version", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    return resp.status == 200
        except Exception:
            return False
    
    # Verify extension is loaded by checking chrome://extensions page
    async def verify_extension_loaded():
        """Verify PraisonAI extension loaded by checking CDP targets and bridge connection."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # Get CDP targets
                async with session.get(f"http://localhost:{port}/json/list", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        targets = await resp.json()
                        
                        # Collect unique extension IDs
                        extension_ids = set()
                        for target in targets:
                            target_url = target.get("url", "")
                            target_title = target.get("title", "")
                            
                            # Quick check for PraisonAI in title
                            if "PraisonAI" in target_title:
                                return True, target_url
                            
                            # Extract extension ID from chrome-extension:// URLs
                            if "chrome-extension://" in target_url:
                                # Extract ID: chrome-extension://<id>/...
                                parts = target_url.replace("chrome-extension://", "").split("/")
                                if parts:
                                    extension_ids.add(parts[0])
                        
                        # Check each extension's manifest to find PraisonAI
                        for ext_id in extension_ids:
                            try:
                                manifest_url = f"http://localhost:{port}/json"
                                # Fetch manifest via extension's background page or direct check
                                # For now, check bridge server health for connection count
                                pass
                            except Exception:
                                pass
                        
                        # Check if bridge server has extension connected
                        try:
                            async with session.get(f"http://localhost:{server_port}/health", timeout=aiohttp.ClientTimeout(total=2)) as health_resp:
                                if health_resp.status == 200:
                                    health = await health_resp.json()
                                    if health.get("connections", 0) > 0:
                                        return True, f"Extension connected to bridge (connections: {health.get('connections')})"
                        except Exception:
                            pass
                        
                        # Extension may be loaded but no bridge connection yet - still consider success if we have extension targets
                        if extension_ids:
                            return True, f"Extension IDs found: {', '.join(list(extension_ids)[:2])}"
                        return True, None
        except Exception as e:
            if debug:
                logging.debug(f"Extension verification error: {e}")
            return False, str(e)
        return False, "No extension targets found"
    
    chrome_ok = asyncio.run(check_chrome())
    if chrome_ok:
        console.print(f"[green]✓ Chrome started with debug port {port}[/green]")
        
        # Verify extension
        ext_loaded, ext_info = asyncio.run(verify_extension_loaded())
        if ext_loaded:
            console.print("[green]✓ Extension loaded via --load-extension[/green]")
            if ext_info and debug:
                console.print(f"   Extension URL: {ext_info}")
        else:
            console.print("[yellow]⚠️ Extension may not have loaded properly[/yellow]")
            if debug and ext_info:
                console.print(f"   Details: {ext_info}")
    else:
        console.print("[yellow]⚠️ Chrome may not have started properly[/yellow]")
    
    # If goal provided, run it
    if goal:
        console.print()
        console.print(f"[bold]Running goal:[/bold] {goal}")
        console.print(f"   [dim]Engine: {engine}[/dim]")
        console.print()
        
        try:
            # Enable vision mode for dynamic screenshot analysis when recording or debug
            enable_vision = record_video or debug
            
            # Initialize profiler if enabled
            profiler_instance = None
            if profile or deep_profile:
                from .profiling import init_profiler
                profiler_instance = init_profiler(enabled=True, deep_profile=deep_profile)
                console.print(f"[cyan]📊 Profiling {'(deep)' if deep_profile else ''} enabled[/cyan]")
            
            # Force screenshot capture if recording video
            if record_video and not screenshot_dir:
                screenshot_dir = Path.home() / ".praisonai" / "browser_screenshots" / datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                console.print(f"[cyan]Recording screenshots to: {screenshot_dir}[/cyan]")
            
            async def run_with_extension():
                """Run goal using extension via bridge server."""
                from .server import run_browser_agent_with_progress
                
                result = await run_browser_agent_with_progress(
                    goal=goal,
                    url=url,
                    model=model,
                    max_steps=max_steps,
                    timeout=timeout,  # Use CLI timeout parameter
                    debug=debug,
                    port=server_port,
                    on_step=lambda step: console.print(f"   [dim]Step {step}...[/dim]") if debug else None,
                )
                return result
            
            async def run_with_cdp():
                """Run goal using direct CDP (fallback)."""
                from .cdp_agent import run_cdp_only
                
                result = await run_cdp_only(
                    goal=goal,
                    url=url,
                    model=model,
                    port=port,
                    max_steps=max_steps,
                    verbose=verbose or debug,
                    debug=debug,
                    screenshot_dir=str(screenshot_dir) if screenshot_dir else None,
                    enable_vision=enable_vision,
                    record_video=record_video,
                    verify_actions=not no_verify,  # Pass verify flag
                )
                return result
            
            async def run_goal():
                """Run goal with engine selection logic."""
                selected_engine = engine.lower()
                
                # Handle explicit engine selection
                if selected_engine == "cdp":
                    console.print("[cyan]Using CDP mode (direct Chrome DevTools Protocol)[/cyan]")
                    return await run_with_cdp()
                
                if selected_engine == "extension":
                    console.print("[cyan]Using Extension mode (via bridge server)[/cyan]")
                    
                    # CRITICAL: Navigate to start URL first to trigger content script
                    # Content scripts don't run on about:blank, so we need to navigate
                    # to an actual page to wake the service worker
                    console.print(f"[dim]Navigating to {url} to wake extension...[/dim]")
                    try:
                        import aiohttp
                        async with aiohttp.ClientSession() as session:
                            # Get page target
                            async with session.get(f"http://localhost:{port}/json") as resp:
                                if resp.status == 200:
                                    targets = await resp.json()
                                    page_target = next((t for t in targets if t.get('type') == 'page'), None)
                                    if page_target:
                                        ws_url = page_target.get('webSocketDebuggerUrl')
                                        if ws_url:
                                            import websockets
                                            async with websockets.connect(ws_url) as ws:
                                                # Enable Page events
                                                await ws.send('{"id":1,"method":"Page.enable"}')
                                                await ws.recv()
                                                
                                                # Navigate to start URL
                                                await ws.send('{"id":2,"method":"Page.navigate","params":{"url":"' + url + '"}}')
                                                await ws.recv()
                                                if debug:
                                                    console.print(f"[dim]   [DEBUG] Navigated to {url} via CDP[/dim]")
                                                
                                                # Wait for page load (up to 5 seconds)
                                                try:
                                                    import async_timeout
                                                    async with async_timeout.timeout(5):
                                                        while True:
                                                            msg = await ws.recv()
                                                            if 'Page.loadEventFired' in msg:
                                                                if debug:
                                                                    console.print("[dim]   [DEBUG] Page loaded, content script should be active[/dim]")
                                                                break
                                                except:
                                                    if debug:
                                                        console.print("[dim]   [DEBUG] Page load event timeout, continuing anyway[/dim]")
                                                
                                                # Wait for content script to inject
                                                await asyncio.sleep(2)
                    except Exception as e:
                        if debug:
                            console.print(f"[dim]   [DEBUG] CDP navigation failed: {e}[/dim]")
                    
                    # CRITICAL: Attach to extension service worker and trigger connection
                    if debug:
                        console.print("[dim]   [DEBUG] Attempting to wake extension service worker via CDP...[/dim]")
                    try:
                        import aiohttp
                        async with aiohttp.ClientSession() as session:
                            async with session.get(f"http://localhost:{port}/json") as resp:
                                if resp.status == 200:
                                    targets = await resp.json()
                                    # Find the PraisonAI extension service worker or background
                                    # Service workers appear in /json/list with type 'service_worker'
                                    extension_target = None
                                    for t in targets:
                                        target_url = t.get('url', '')
                                        target_type = t.get('type', '')
                                        
                                        if debug:
                                            if 'chrome-extension' in target_url:
                                                console.print(f"[dim]   [DEBUG] Extension target: {target_type} - {target_url[:60]}[/dim]")
                                        
                                        # Prefer service_worker type, fall back to background_page
                                        if 'chrome-extension' in target_url and 'PraisonAI' not in target_url:
                                            # Skip built-in extensions like TTS
                                            if 'fignfifoniblkonapihmkfakmlgkbkcf' in target_url:
                                                continue
                                            # Found a non-builtin extension target
                                            if target_type == 'service_worker' or extension_target is None:
                                                extension_target = t
                                    
                                    if extension_target:
                                        ws_url = extension_target.get('webSocketDebuggerUrl')
                                        target_url = extension_target.get('url', '')[:50]
                                        target_type = extension_target.get('type', '')
                                        if ws_url:
                                            if debug:
                                                console.print(f"[green]   [DEBUG] Using target: {target_type} - {target_url}[/green]")
                                                try:
                                                    import websockets
                                                    async with websockets.connect(ws_url) as ws:
                                                        # Enable Runtime and trigger bridge connection
                                                        await ws.send('{"id":1,"method":"Runtime.enable"}')
                                                        await ws.recv()
                                                        import json
                                                        wake_expr = 'console.log("[CDP-WAKE] Triggering bridge connection..."); typeof initBridgeConnection !== "undefined" ? initBridgeConnection() : "initBridgeConnection not found";'
                                                        wake_cmd = json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {"expression": wake_expr, "awaitPromise": True}})
                                                        await ws.send(wake_cmd)
                                                        response = await ws.recv()
                                                        if debug:
                                                            console.print(f"[dim]   [DEBUG] Runtime.evaluate response: {response[:200]}...[/dim]")
                                                            console.print("[green]   [DEBUG] ✓ Sent wake command to extension service worker[/green]")
                                                except Exception as we:
                                                    if debug:
                                                        console.print(f"[dim]   [DEBUG] Could not connect to extension target: {we}[/dim]")
                    except Exception as e:
                        if debug:
                            console.print(f"[dim]   [DEBUG] Extension wake attempt failed: {e}[/dim]")
                    
                    # Wait for extension to process the wake command and connect
                    await asyncio.sleep(3)
                    
                    # Wait for extension to connect to bridge server
                    extension_connected = False
                    wait_start = asyncio.get_event_loop().time()
                    max_wait = 30.0  # Wait up to 30 seconds for extension to connect
                    
                    console.print("[dim]Waiting for extension to connect to bridge server...[/dim]")
                    
                    # Detailed logging for debugging
                    if debug:
                        console.print("[dim]   [DEBUG] Bridge server URL: http://localhost:{server_port}/health[/dim]")
                        console.print("[dim]   [DEBUG] Checking CDP targets for service worker...[/dim]")
                        try:
                            import aiohttp
                            async with aiohttp.ClientSession() as session:
                                async with session.get(f"http://localhost:{port}/json", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                                    if resp.status == 200:
                                        targets = await resp.json()
                                        console.print(f"[dim]   [DEBUG] CDP targets found: {len(targets)}[/dim]")
                                        for t in targets:
                                            target_type = t.get('type', 'unknown')
                                            target_url = t.get('url', '')[:60]
                                            console.print(f"[dim]   [DEBUG]   - [{target_type}] {target_url}[/dim]")
                                        # Check for service worker specifically
                                        sw_targets = [t for t in targets if t.get('type') == 'service_worker']
                                        if sw_targets:
                                            console.print(f"[green]   [DEBUG] ✓ Service worker found: {len(sw_targets)}[/green]")
                                        else:
                                            console.print("[yellow]   [DEBUG] ⚠ No service_worker targets found - extension may not have loaded[/yellow]")
                        except Exception as e:
                            console.print(f"[dim]   [DEBUG] CDP target check failed: {e}[/dim]")
                    
                    import aiohttp
                    check_count = 0
                    while asyncio.get_event_loop().time() - wait_start < max_wait:
                        try:
                            async with aiohttp.ClientSession() as session:
                                async with session.get(
                                    f"http://localhost:{server_port}/health",
                                    timeout=aiohttp.ClientTimeout(total=2)
                                ) as resp:
                                    if resp.status == 200:
                                        health = await resp.json()
                                        connections = health.get("connections", 0)
                                        sessions = health.get("sessions", 0)
                                        if connections >= 1:
                                            extension_connected = True
                                            console.print(f"[green]✓ Extension connected ({connections} connection(s), {sessions} session(s))[/green]")
                                            break
                                        else:
                                            check_count += 1
                                            if check_count == 1 or (check_count % 3 == 0):
                                                elapsed = int(asyncio.get_event_loop().time() - wait_start)
                                                console.print(f"[dim]   No extension connections yet ({elapsed}s)...[/dim]")
                                                if debug and check_count == 1:
                                                    console.print("[dim]   [DEBUG] Extension service worker may not be running[/dim]")
                                                    console.print("[dim]   [DEBUG] Try: chrome://extensions/ -> PraisonAI -> Click 'Reload'[/dim]")
                        except Exception as e:
                            if debug:
                                console.print(f"[dim]   [DEBUG] Health check error: {e}[/dim]")
                        
                        await asyncio.sleep(1.0)  # Check every second
                    
                    if not extension_connected:
                        elapsed = int(asyncio.get_event_loop().time() - wait_start)
                        console.print(f"[red]✗ Extension did not connect after {elapsed}s[/red]")
                        console.print("[yellow]Hint: Open Chrome DevTools -> Extensions -> PraisonAI -> Background page to check console[/yellow]")
                        
                        # Additional debug info
                        if debug:
                            console.print("[dim]   [DEBUG] Root cause: Chrome MV3 service workers are lazy-loaded[/dim]")
                            console.print("[dim]   [DEBUG] The service worker may terminate before connecting to bridge[/dim]")
                            console.print("[dim]   [DEBUG] Workaround: Use --engine cdp for reliable automation[/dim]")
                        
                        raise Exception(f"Extension not connected to bridge server after {elapsed}s. Try: 1) Reload the extension 2) Check extension console for errors")
                    
                    try:
                        result = await run_with_extension()
                        if not result.get("error"):
                            return result
                        console.print(f"[yellow]Extension mode failed: {result.get('error')}[/yellow]")
                        raise Exception(result.get("error", "Extension mode failed"))
                    except Exception as e:
                        console.print(f"[red]Extension mode error: {e}[/red]")
                        raise
                
                # Auto mode: try extension first, fall back to CDP
                if selected_engine == "auto":
                    # Check if extension is connected to bridge server
                    extension_available = False
                    try:
                        import aiohttp
                        async with aiohttp.ClientSession() as session:
                            async with session.get(
                                f"http://localhost:{server_port}/health",
                                timeout=aiohttp.ClientTimeout(total=2)
                            ) as resp:
                                if resp.status == 200:
                                    health = await resp.json()
                                    # Need at least 1 connection (the extension)
                                    # Note: CLI will add another connection when it sends the goal
                                    extension_available = health.get("connections", 0) >= 1
                                    if debug:
                                        console.print(f"[dim]Bridge server: {health}[/dim]")
                    except Exception as e:
                        if debug:
                            console.print(f"[dim]Bridge server check failed: {e}[/dim]")
                    
                    if extension_available:
                        console.print("[green]🧩 Using Extension mode (extension connected)[/green]")
                        try:
                            # Wait a moment for extension to fully initialize
                            await asyncio.sleep(0.5)
                            result = await run_with_extension()
                            if result.get("success") or not result.get("error"):
                                result["engine"] = "extension"
                                return result
                            # Extension returned error, try CDP
                            console.print(f"[yellow]Extension mode incomplete, falling back to CDP[/yellow]")
                            if debug:
                                console.print(f"[dim]Extension error: {result.get('error')}[/dim]")
                        except asyncio.TimeoutError:
                            console.print("[yellow]Extension timed out, falling back to CDP[/yellow]")
                        except Exception as e:
                            console.print(f"[yellow]Extension error, falling back to CDP: {e}[/yellow]")
                            if debug:
                                import traceback
                                traceback.print_exc()
                    else:
                        console.print("[cyan]🔌 Using CDP mode (extension not connected)[/cyan]")
                    
                    # Fallback to CDP
                    result = await run_with_cdp()
                    result["engine"] = "cdp"
                    return result
                
                # Unknown engine, use CDP
                console.print(f"[yellow]Unknown engine '{engine}', using CDP[/yellow]")
                return await run_with_cdp()
            
            result = asyncio.run(run_goal())
            
            # Check for video output - prefer WebM from CDP screencast over GIF fallback
            if record_video and screenshot_dir:
                webm_path = Path(screenshot_dir) / "recording.webm"
                gif_path = Path(screenshot_dir) / "recording.gif"
                
                # Check if WebM was created by CDP screencast (real video)
                if webm_path.exists():
                    console.print(f"[green]📹 Video recording saved: {webm_path}[/green]")
                else:
                    # Fallback: create GIF from screenshots
                    try:
                        from .video import create_video_from_screenshots, check_ffmpeg_available
                        if not check_ffmpeg_available():
                            console.print("[yellow]FFmpeg not installed - creating GIF fallback[/yellow]")
                        video_path = create_video_from_screenshots(str(screenshot_dir))
                        if video_path:
                            console.print(f"[green]📹 Video recording saved: {video_path}[/green]")
                        else:
                            console.print(f"[yellow]Screenshots saved to: {screenshot_dir}[/yellow]")
                    except Exception as e:
                        console.print(f"[yellow]Video creation failed: {e}[/yellow]")
                        console.print(f"[dim]Screenshots saved to: {screenshot_dir}[/dim]")
            
            if result.get("success"):
                engine_used = result.get("engine", "cdp")
                engine_icon = "🧩" if engine_used == "extension" else "🔌"
                console.print(f"\n[green]✅ Task completed in {result.get('steps', '?')} steps[/green]")
                if result.get("summary"):
                    console.print(f"   {result['summary']}")
                console.print(f"   Final URL: {result.get('final_url', 'N/A')}")
                console.print(f"   [dim]Engine: {engine_icon} {engine_used.upper()}[/dim]")
            else:
                console.print(f"\n[red]❌ Task failed:[/red] {result.get('error', 'Unknown error')}")
            
            # Show profiling report if enabled
            if profile or deep_profile:
                try:
                    from .profiling import stop_profiler
                    profile_report = stop_profiler()
                    if profile_report:
                        console.print(profile_report)
                except Exception as e:
                    if debug:
                        console.print(f"[dim]Profiling report error: {e}[/dim]")
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
        
        # Cleanup
        console.print("\n[dim]Cleaning up...[/dim]")
        try:
            chrome_process.terminate()
            chrome_process.wait(timeout=5)
        except Exception:
            try:
                chrome_process.kill()
            except Exception:
                pass
        
        if server_process:
            try:
                server_process.terminate()
                server_process.wait(timeout=5)
            except Exception:
                pass
        
        # Clean temp profile (preserve persistent profiles)
        if not using_persistent_profile:
            try:
                shutil.rmtree(profile_dir)
            except Exception:
                pass
        
        console.print("[green]Done[/green]")
    else:
        # No goal - run interactive chat mode
        console.print()
        console.print("[bold green]Chrome is ready![/bold green]")
        console.print()
        console.print("[bold]Interactive Browser Mode[/bold]")
        console.print("Type goals to execute (or 'exit', 'quit', 'q' to stop)")
        console.print()
        
        # Interactive chat loop
        goal_count = 0
        while True:
            try:
                # Prompt for goal
                goal_input = console.input("[bold cyan]Goal> [/bold cyan]")
                goal_input = goal_input.strip()
                
                # Exit commands
                if goal_input.lower() in ("exit", "quit", "q", ""):
                    if goal_input == "":
                        continue  # Empty input, keep waiting
                    console.print("\n[yellow]Exiting...[/yellow]")
                    break
                
                # Help command
                if goal_input.lower() in ("help", "?"):
                    console.print()
                    console.print("[bold]Commands:[/bold]")
                    console.print("  [cyan]<goal>[/cyan]  - Execute a browser goal")
                    console.print("  [cyan]exit[/cyan]   - Stop and cleanup")
                    console.print("  [cyan]help[/cyan]   - Show this help")
                    console.print()
                    console.print("[bold]Example goals:[/bold]")
                    console.print('  "Search for PraisonAI on Google"')
                    console.print('  "Click the first result"')
                    console.print('  "Go to wikipedia.org"')
                    console.print()
                    continue
                
                # Execute goal
                goal_count += 1
                console.print(f"\n[dim]Executing goal #{goal_count} ({engine})...[/dim]\n")
                
                try:
                    # Setup screenshot dir for this goal if recording
                    goal_screenshot_dir = None
                    if record_video or screenshot:
                        goal_screenshot_dir = Path.home() / ".praisonai" / "browser_screenshots" / f"goal_{goal_count}_{datetime.now().strftime('%H%M%S')}"
                        goal_screenshot_dir.mkdir(parents=True, exist_ok=True)
                    
                    async def run_interactive_goal():
                        """Run goal with engine selection for interactive mode."""
                        selected_engine = engine.lower()
                        
                        # Extension mode
                        if selected_engine in ("extension", "auto"):
                            try:
                                from .server import run_browser_agent_with_progress
                                result = await run_browser_agent_with_progress(
                                    goal=goal_input,
                                    url=url,  # Can use current page context
                                    model=model,
                                    max_steps=max_steps,
                                    timeout=timeout,  # Use CLI timeout parameter
                                    debug=debug,
                                    port=server_port,
                                )
                                if result.get("success") or not result.get("error"):
                                    result["engine"] = "extension"
                                    return result
                                # Fall through to CDP on error
                                if selected_engine == "extension":
                                    return result  # Don't fallback if explicitly requested
                            except Exception as e:
                                console.print(f"[dim]Extension: {e}[/dim]")
                                if selected_engine == "extension":
                                    raise
                        
                        # CDP fallback
                        from .cdp_agent import run_cdp_only
                        result = await run_cdp_only(
                            goal=goal_input,
                            url=None,  # Use current page
                            model=model,
                            port=port,
                            max_steps=max_steps,
                            verbose=verbose or debug,
                            debug=debug,
                            screenshot_dir=str(goal_screenshot_dir) if goal_screenshot_dir else None,
                            enable_vision=debug or record_video,
                        )
                        result["engine"] = "cdp"
                        return result
                    
                    result = asyncio.run(run_interactive_goal())
                    
                    # Create video if recording
                    if record_video and goal_screenshot_dir:
                        try:
                            from .video import create_video_from_screenshots
                            video_path = create_video_from_screenshots(str(goal_screenshot_dir))
                            if video_path:
                                console.print(f"[green]📹 Video: {video_path}[/green]")
                        except Exception as e:
                            if debug:
                                console.print(f"[dim]Video creation failed: {e}[/dim]")
                    
                    # Show result
                    if result.get("success"):
                        engine_icon = "🧩" if result.get("engine") == "extension" else "🔌"
                        console.print(f"[green]✅ Done in {result.get('steps', '?')} steps ({engine_icon})[/green]")
                        if result.get("summary"):
                            console.print(f"   {result['summary'][:100]}")
                    else:
                        console.print(f"[red]❌ Failed: {result.get('error', 'Unknown')[:80]}[/red]")
                    
                    console.print()
                    
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]\n")
                
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]\n")
            except EOFError:
                break
        
        # Cleanup
        console.print("\n[dim]Cleaning up...[/dim]")
        try:
            chrome_process.terminate()
            chrome_process.wait(timeout=5)
        except Exception:
            try:
                chrome_process.kill()
            except Exception:
                pass
        
        if server_process:
            try:
                server_process.terminate()
                server_process.wait(timeout=5)
            except Exception:
                pass
        
        # Clean temp profile (preserve persistent profiles)
        if not using_persistent_profile:
            try:
                shutil.rmtree(profile_dir)
            except Exception:
                pass
        
        console.print(f"[green]Completed {goal_count} goal(s)[/green]")


# Register benchmark commands
try:
    from .benchmark import add_benchmark_commands
    add_benchmark_commands(app)
except ImportError:
    pass  # Benchmark module not available


if __name__ == "__main__":
    app()

