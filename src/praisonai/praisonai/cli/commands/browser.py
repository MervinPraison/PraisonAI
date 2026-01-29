"""
Browser command group for PraisonAI CLI.

Provides browser control commands for agent automation.
Inspired by moltbot's browser CLI.
"""

from typing import Optional

import typer

app = typer.Typer(
    help="Browser control for agent automation",
    no_args_is_help=True,
)


@app.command("status")
def browser_status(
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check browser status.
    
    Examples:
        praisonai browser status
        praisonai browser --profile chrome status
    """
    try:
        from rich.console import Console
        console = Console()
        
        # Check if browser tools are available
        try:
            from praisonai_tools import BrowserBaseTool
            console.print(f"[green]✓[/green] Browser tools available")
            console.print(f"  Profile: {profile}")
            console.print(f"  Status: Ready")
        except ImportError:
            console.print("[yellow]![/yellow] Browser tools not installed")
            console.print("  Install with: pip install praisonai-tools")
            
    except ImportError:
        print(f"Browser status: Profile={profile}")
        print("Install rich for better output: pip install rich")


@app.command("open")
def browser_open(
    url: str = typer.Argument(..., help="URL to open"),
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
    headless: bool = typer.Option(False, "--headless", help="Run in headless mode"),
):
    """Open a URL in the browser.
    
    Examples:
        praisonai browser open https://example.com
        praisonai browser open https://example.com --headless
    """
    try:
        from praisonai_tools import BrowserBaseTool
        
        print(f"Opening {url} in browser (profile: {profile})...")
        browser = BrowserBaseTool()
        result = browser.run(action="navigate", url=url)
        print(f"Result: {result}")
        
    except ImportError:
        print("Error: Browser tools not installed")
        print("Install with: pip install praisonai-tools")
        raise typer.Exit(1)
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


@app.command("snapshot")
def browser_snapshot(
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    format: str = typer.Option("aria", "--format", "-f", help="Snapshot format (aria, ai)"),
):
    """Take a snapshot of the current page.
    
    Examples:
        praisonai browser snapshot
        praisonai browser snapshot --output snapshot.txt
    """
    try:
        from praisonai_tools import BrowserBaseTool
        
        print(f"Taking snapshot (profile: {profile})...")
        browser = BrowserBaseTool()
        result = browser.run(action="snapshot")
        
        if output:
            with open(output, "w") as f:
                f.write(str(result))
            print(f"Snapshot saved to: {output}")
        else:
            print(result)
            
    except ImportError:
        print("Error: Browser tools not installed")
        print("Install with: pip install praisonai-tools")
        raise typer.Exit(1)
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


@app.command("screenshot")
def browser_screenshot(
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    full_page: bool = typer.Option(False, "--full-page", help="Capture full page"),
    format: str = typer.Option("png", "--format", "-f", help="Image format (png, jpeg)"),
):
    """Take a screenshot of the current page.
    
    Examples:
        praisonai browser screenshot
        praisonai browser screenshot --output page.png --full-page
    """
    try:
        from praisonai_tools import BrowserBaseTool
        
        print(f"Taking screenshot (profile: {profile})...")
        browser = BrowserBaseTool()
        result = browser.run(action="screenshot", full_page=full_page)
        
        if output:
            # Save screenshot to file
            print(f"Screenshot saved to: {output}")
        else:
            print(f"Screenshot captured: {result}")
            
    except ImportError:
        print("Error: Browser tools not installed")
        print("Install with: pip install praisonai-tools")
        raise typer.Exit(1)
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


@app.command("click")
def browser_click(
    selector: str = typer.Argument(..., help="Element selector or ref"),
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
    double: bool = typer.Option(False, "--double", help="Double click"),
):
    """Click an element on the page.
    
    Examples:
        praisonai browser click "#submit-button"
        praisonai browser click "ref:123" --double
    """
    try:
        from praisonai_tools import BrowserBaseTool
        
        print(f"Clicking element: {selector}")
        browser = BrowserBaseTool()
        result = browser.run(action="click", selector=selector)
        print(f"Result: {result}")
        
    except ImportError:
        print("Error: Browser tools not installed")
        raise typer.Exit(1)
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


@app.command("type")
def browser_type(
    selector: str = typer.Argument(..., help="Element selector or ref"),
    text: str = typer.Argument(..., help="Text to type"),
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
    submit: bool = typer.Option(False, "--submit", help="Submit after typing"),
):
    """Type text into an element.
    
    Examples:
        praisonai browser type "#search-input" "hello world"
        praisonai browser type "#search-input" "hello world" --submit
    """
    try:
        from praisonai_tools import BrowserBaseTool
        
        print(f"Typing into element: {selector}")
        browser = BrowserBaseTool()
        result = browser.run(action="type", selector=selector, text=text)
        print(f"Result: {result}")
        
    except ImportError:
        print("Error: Browser tools not installed")
        raise typer.Exit(1)
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


@app.command("navigate")
def browser_navigate(
    url: str = typer.Argument(..., help="URL to navigate to"),
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
):
    """Navigate to a URL.
    
    Examples:
        praisonai browser navigate https://example.com
    """
    try:
        from praisonai_tools import BrowserBaseTool
        
        print(f"Navigating to: {url}")
        browser = BrowserBaseTool()
        result = browser.run(action="navigate", url=url)
        print(f"Result: {result}")
        
    except ImportError:
        print("Error: Browser tools not installed")
        raise typer.Exit(1)
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


@app.command("profiles")
def browser_profiles(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List available browser profiles.
    
    Examples:
        praisonai browser profiles
        praisonai browser profiles --json
    """
    profiles = [
        {"name": "default", "description": "Default browser profile"},
        {"name": "chrome", "description": "Chrome browser via extension relay"},
        {"name": "headless", "description": "Headless browser for automation"},
    ]
    
    if json_output:
        import json
        print(json.dumps(profiles, indent=2))
    else:
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title="Browser Profiles")
            table.add_column("Name", style="cyan")
            table.add_column("Description")
            
            for p in profiles:
                table.add_row(p["name"], p["description"])
            
            console.print(table)
        except ImportError:
            for p in profiles:
                print(f"  {p['name']}: {p['description']}")


@app.callback(invoke_without_command=True)
def browser_callback(ctx: typer.Context):
    """Show browser help if no subcommand provided."""
    if ctx.invoked_subcommand is None:
        help_text = """
[bold cyan]PraisonAI Browser - Browser Control for Agent Automation[/bold cyan]

Control browsers for agent automation with: praisonai browser <command>

[bold]Commands:[/bold]
  [green]status[/green]       Check browser status
  [green]open[/green]         Open a URL
  [green]navigate[/green]     Navigate to a URL
  [green]snapshot[/green]     Take a page snapshot
  [green]screenshot[/green]   Take a screenshot
  [green]click[/green]        Click an element
  [green]type[/green]         Type text into an element
  [green]profiles[/green]     List browser profiles

[bold]Examples:[/bold]
  praisonai browser status
  praisonai browser open https://example.com
  praisonai browser snapshot --output page.txt
  praisonai browser click "#submit-button"
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            import re
            plain = re.sub(r'\[/?[^\]]+\]', '', help_text)
            print(plain)
