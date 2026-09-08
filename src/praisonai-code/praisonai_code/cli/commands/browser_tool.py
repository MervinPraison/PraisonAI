"""
Browser command group for PraisonAI CLI.

Provides browser control commands for agent automation.
Inspired by moltbot's browser CLI.

Every subcommand here drives ``praisonai_tools.BrowserBaseTool``, whose ``run``
reports failure by *returning* a value (``{"error": "Unknown action: click"}``)
rather than raising. Printing that return value and falling off the end of the
function therefore exits 0 for work that never happened, so results go through
``_require_success`` and output paths are verified after writing.
"""

import json
import os
from typing import Any, Optional

import typer

app = typer.Typer(
    help="Browser control for agent automation",
    no_args_is_help=True,
)

_NOT_INSTALLED = (
    "Error: Browser tools not installed\nInstall with: pip install praisonai-tools"
)


class _BrowserError(RuntimeError):
    """A browser action reported failure (by return value or by raising)."""


def _load_browser():
    """Return a BrowserBaseTool instance, or exit 1 with install instructions."""
    try:
        from praisonai_tools import BrowserBaseTool
    except ImportError:
        print(_NOT_INSTALLED)
        raise typer.Exit(1)
    return BrowserBaseTool()


def _result_error(result: Any) -> Optional[str]:
    """Return the failure message carried by ``result``, or None if it succeeded.

    ``BrowserBaseTool.run`` signals failure in-band and differently by version:
    older builds raise, newer ones return ``{"error": ...}`` or a string that
    begins with "Error". All three must end up non-zero.
    """
    if result is None:
        return "browser returned no result"
    if isinstance(result, dict):
        for key in ("error", "err"):
            if result.get(key):
                return str(result[key])
        if result.get("ok") is False or result.get("success") is False:
            return str(result.get("message") or result)
        return None
    if isinstance(result, str):
        stripped = result.strip()
        lowered = stripped.lower()
        if lowered.startswith(("error", "unknown action", "unsupported action")):
            return stripped
    return None


def _requested(**flags) -> dict:
    """Keep only the options the user actually changed from their default.

    Forwarding every flag unconditionally would break against a
    ``praisonai-tools`` build whose ``run`` does not accept them. Forwarding
    none is what made ``--headless``/``--double``/``--submit``/``--format``
    no-ops. So: an untouched default is dropped, and a flag the user typed is
    forwarded and reported if the installed tool cannot honour it.
    """
    return {k: v for k, v in flags.items() if v not in (None, False, "")}


def _run_action(browser, action: str, **kwargs) -> Any:
    """Invoke one browser action, converting every failure mode into an exception.

    Unsupported keyword arguments are reported rather than dropped: a flag the
    installed ``praisonai-tools`` cannot honour must not look like it worked.
    """
    try:
        result = browser.run(action=action, **kwargs)
    except TypeError as e:
        raise _BrowserError(
            f"the installed praisonai-tools does not support "
            f"{action}({', '.join(sorted(kwargs))}): {e}"
        ) from e
    except Exception as e:
        raise _BrowserError(str(e)) from e

    error = _result_error(result)
    if error:
        raise _BrowserError(error)
    return result


def _profile_arg(profile: str) -> Optional[str]:
    """``--profile default`` is the implicit default, so it is not an ask."""
    return None if profile == "default" else profile


def _fail(message: str) -> None:
    print(f"Error: {message}")
    raise typer.Exit(1)


def _write_text_output(result: Any, output: str, label: str) -> None:
    """Write textual page content to ``output``, or fail loudly."""
    text = result if isinstance(result, str) else None
    if text is None and isinstance(result, dict):
        for key in ("text", "content", "snapshot", "data"):
            if isinstance(result.get(key), str):
                text = result[key]
                break
    if text is None:
        _fail(
            f"{label} returned no page text to write "
            f"({type(result).__name__}); nothing was saved to {output}"
        )
    with open(output, "w") as f:
        f.write(text)
    print(f"{label} saved to: {output}")


def _screenshot_bytes(result: Any) -> Optional[bytes]:
    """Extract image bytes from a screenshot result, across tool versions."""
    if isinstance(result, (bytes, bytearray)):
        return bytes(result)
    if isinstance(result, dict):
        for key in ("bytes", "image", "data", "screenshot"):
            value = result.get(key)
            if isinstance(value, (bytes, bytearray)):
                return bytes(value)
            if isinstance(value, str) and value:
                decoded = _maybe_base64(value)
                if decoded is not None:
                    return decoded
        for key in ("path", "file", "filename", "output"):
            value = result.get(key)
            if isinstance(value, str) and os.path.isfile(value):
                with open(value, "rb") as f:
                    return f.read()
    if isinstance(result, str):
        if os.path.isfile(result):
            with open(result, "rb") as f:
                return f.read()
        decoded = _maybe_base64(result)
        if decoded is not None:
            return decoded
    return None


def _maybe_base64(value: str) -> Optional[bytes]:
    """Decode a base64 (or data: URI) payload, or return None if it is not one."""
    import base64
    import binascii

    payload = value.split(",", 1)[1] if value.startswith("data:") else value
    if len(payload) < 32:
        return None
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return None


@app.command("status")
def browser_status(
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check browser status.

    Examples:
        praisonai browser-tool status
        praisonai browser-tool --profile chrome status
    """
    try:
        from praisonai_tools import BrowserBaseTool  # noqa: F401

        available = True
    except ImportError:
        available = False

    if json_output:
        print(json.dumps(
            {
                "available": available,
                "profile": profile,
                "status": "ready" if available else "not_installed",
            },
            indent=2,
        ))
        return

    try:
        from rich.console import Console

        console = Console()
        if available:
            console.print("[green]✓[/green] Browser tools available")
            console.print(f"  Profile: {profile}")
            console.print("  Status: Ready")
        else:
            console.print("[yellow]![/yellow] Browser tools not installed")
            console.print("  Install with: pip install praisonai-tools")
    except ImportError:
        print(f"Browser status: Profile={profile}")
        print("Available" if available else "Not installed")


@app.command("open")
def browser_open(
    url: str = typer.Argument(..., help="URL to open"),
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
    headless: bool = typer.Option(False, "--headless", help="Run in headless mode"),
):
    """Open a URL in the browser.

    Examples:
        praisonai browser-tool open https://example.com
        praisonai browser-tool open https://example.com --headless
    """
    browser = _load_browser()
    print(f"Opening {url} in browser (profile: {profile})...")
    try:
        result = _run_action(
            browser, "navigate", url=url,
            **_requested(profile=_profile_arg(profile), headless=headless),
        )
    except _BrowserError as e:
        _fail(str(e))
    print(f"Result: {result}")


@app.command("snapshot")
def browser_snapshot(
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    format: str = typer.Option("aria", "--format", "-f", help="Snapshot format (aria, ai)"),
):
    """Take a snapshot of the current page.

    Examples:
        praisonai browser-tool snapshot
        praisonai browser-tool snapshot --output snapshot.txt
    """
    browser = _load_browser()
    print(f"Taking snapshot (profile: {profile})...")
    try:
        result = _run_action(
            browser, "snapshot",
            **_requested(profile=_profile_arg(profile),
                         format=None if format == "aria" else format),
        )
    except _BrowserError as e:
        _fail(str(e))

    if output:
        _write_text_output(result, output, "Snapshot")
    else:
        print(result)


@app.command("screenshot")
def browser_screenshot(
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    full_page: bool = typer.Option(False, "--full-page", help="Capture full page"),
    format: str = typer.Option("png", "--format", "-f", help="Image format (png, jpeg)"),
):
    """Take a screenshot of the current page.

    Examples:
        praisonai browser-tool screenshot
        praisonai browser-tool screenshot --output page.png --full-page
    """
    browser = _load_browser()
    print(f"Taking screenshot (profile: {profile})...")
    try:
        result = _run_action(
            browser,
            "screenshot",
            full_page=full_page,
            **_requested(profile=_profile_arg(profile),
                         format=None if format == "png" else format),
        )
    except _BrowserError as e:
        _fail(str(e))

    if not output:
        print(f"Screenshot captured: {result}")
        return

    # This branch used to print "Screenshot saved to: {output}" without writing
    # anything at all, so `--output shot.png` reported success and left no file.
    data = _screenshot_bytes(result)
    if data is None:
        _fail(
            f"screenshot returned no image data ({type(result).__name__}); "
            f"nothing was saved to {output}"
        )
    with open(output, "wb") as f:
        f.write(data)
    print(f"Screenshot saved to: {output}")


@app.command("click")
def browser_click(
    selector: str = typer.Argument(..., help="Element selector or ref"),
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
    double: bool = typer.Option(False, "--double", help="Double click"),
):
    """Click an element on the page.

    Examples:
        praisonai browser-tool click "#submit-button"
        praisonai browser-tool click "ref:123" --double
    """
    browser = _load_browser()
    print(f"{'Double-clicking' if double else 'Clicking'} element: {selector}")
    try:
        result = _run_action(
            browser, "click", selector=selector,
            **_requested(profile=_profile_arg(profile), double=double),
        )
    except _BrowserError as e:
        _fail(str(e))
    print(f"Result: {result}")


@app.command("type")
def browser_type(
    selector: str = typer.Argument(..., help="Element selector or ref"),
    text: str = typer.Argument(..., help="Text to type"),
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
    submit: bool = typer.Option(False, "--submit", help="Submit after typing"),
):
    """Type text into an element.

    Examples:
        praisonai browser-tool type "#search-input" "hello world"
        praisonai browser-tool type "#search-input" "hello world" --submit
    """
    browser = _load_browser()
    print(f"Typing into element: {selector}")
    try:
        result = _run_action(
            browser,
            "type",
            selector=selector,
            text=text,
            **_requested(profile=_profile_arg(profile), submit=submit),
        )
    except _BrowserError as e:
        _fail(str(e))
    print(f"Result: {result}")


@app.command("navigate")
def browser_navigate(
    url: str = typer.Argument(..., help="URL to navigate to"),
    profile: str = typer.Option("default", "--profile", "-p", help="Browser profile name"),
):
    """Navigate to a URL.

    Examples:
        praisonai browser-tool navigate https://example.com
    """
    browser = _load_browser()
    print(f"Navigating to: {url}")
    try:
        result = _run_action(
            browser, "navigate", url=url,
            **_requested(profile=_profile_arg(profile)),
        )
    except _BrowserError as e:
        _fail(str(e))
    print(f"Result: {result}")


@app.command("profiles")
def browser_profiles(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List available browser profiles.

    Examples:
        praisonai browser-tool profiles
        praisonai browser-tool profiles --json
    """
    profiles = [
        {"name": "default", "description": "Default browser profile"},
        {"name": "chrome", "description": "Chrome browser via extension relay"},
        {"name": "headless", "description": "Headless browser for automation"},
    ]

    if json_output:
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

Control browsers for agent automation with: praisonai browser-tool <command>

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
  praisonai browser-tool status
  praisonai browser-tool open https://example.com
  praisonai browser-tool snapshot --output page.txt
  praisonai browser-tool click "#submit-button"
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            import re
            plain = re.sub(r'\[/?[^\]]+\]', '', help_text)
            print(plain)
