# __main__.py
"""
PraisonAI CLI — Unified Entry Point.

Single entry point for all CLI invocations.
Routes to Typer-based commands for known subcommands,
falls back to legacy argparse for direct prompts and YAML files.

Design:
  - Typer-first: all registered commands auto-discovered via Click
  - Legacy fallback: prompts, .yaml paths, and deprecated --flags
  - No manual command lists needed — adding a Typer command Just Works
"""

import sys
import threading


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_typer_commands_cache = None
_typer_commands_lock = threading.Lock()


def _get_typer_commands():
    """Auto-discover registered Typer commands via Click introspection."""
    global _typer_commands_cache

    # Fast path
    if _typer_commands_cache is not None:
        return _typer_commands_cache

    with _typer_commands_lock:
        if _typer_commands_cache is not None:  # Double-check
            return _typer_commands_cache

        try:
            from praisonai.cli.app import app, register_commands
            register_commands()

            import typer.main
            import click
            click_app = typer.main.get_command(app)
            ctx = click.Context(click_app, info_name="praisonai")
            commands = set(click_app.list_commands(ctx))
        except Exception:
            # Do NOT poison the cache on failure — let the next caller retry.
            import logging
            logging.getLogger("praisonai.__main__").warning(
                "Typer command discovery failed; falling back to legacy dispatch.",
                exc_info=True,
            )
            return set()

        _typer_commands_cache = commands
        return _typer_commands_cache


def _find_first_command(argv):
    """Find the first non-flag argument in argv.

    Skips global flags (--json, --verbose, etc.) and their values.
    Returns the first positional arg, or None if only flags are present.
    """
    # Flags that consume a following value
    VALUE_FLAGS = {"--output-format", "-o"}

    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg.startswith("-"):
            if arg in VALUE_FLAGS:
                skip_next = True
            continue
        return arg  # First non-flag arg
    return None


def _run_typer(argv):
    """Dispatch to the Typer CLI app."""
    import os
    
    # Set up safer encoding for Windows legacy terminals
    if sys.platform == "win32" and hasattr(sys.stdout, 'encoding'):
        encoding = getattr(sys.stdout, 'encoding', '').lower()
        if encoding in ('cp1252', 'cp1251', 'cp850', 'ascii') or ('cp' in encoding and encoding != 'cp65001'):
            # Force UTF-8 mode for subprocess safety
            if 'PYTHONIOENCODING' not in os.environ:
                os.environ['PYTHONIOENCODING'] = 'utf-8'
    
    from praisonai.cli.app import app, register_commands
    register_commands()  # idempotent

    original = sys.argv
    sys.argv = ["praisonai"] + list(argv)
    try:
        app()
    except UnicodeEncodeError as e:
        # Handle Unicode encoding errors gracefully
        print("Error: Unable to display help due to terminal encoding limitations.", file=sys.stderr)
        print("Try setting: $env:PYTHONIOENCODING='utf-8' (PowerShell) or set PYTHONIOENCODING=utf-8 (cmd)", file=sys.stderr)
        sys.exit(0)
    except SystemExit as e:
        sys.exit(e.code if isinstance(e.code, int) else 0)
    finally:
        sys.argv = original


def _run_legacy(argv):
    """Dispatch to the legacy argparse CLI (prompts, YAML, deprecated flags)."""
    from praisonai.cli.main import PraisonAI

    original = sys.argv
    sys.argv = ["praisonai"] + list(argv)
    try:
        praison = PraisonAI()
        result = praison.main()
        code = 0 if result is None else (1 if result is False else 0)
        sys.exit(code)
    except SystemExit as e:
        sys.exit(e.code if isinstance(e.code, int) else 0)
    finally:
        sys.argv = original


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """Unified CLI entry point — Typer-first, legacy fallback.

    Routing rules (in order):
      1. --version / -V          → print version and exit
      2. --help / -h             → Typer help (global or command-level)
      3. No arguments            → Typer interactive TUI
      4. First arg is a Typer cmd→ Typer (auto-discovered from app.py)
      5. Everything else         → Legacy (prompt, .yaml, deprecated flags)
    """
    argv = sys.argv[1:]

    # 1. Quick version check (minimal imports)
    if "--version" in argv or "-V" in argv:
        from praisonai.version import __version__
        print(f"PraisonAI version {__version__}")
        return

    # 2. Help flags → always Typer (global help or command help)
    if "--help" in argv or "-h" in argv:
        _run_typer(argv)
        return

    # 3. No arguments → Typer (interactive TUI)
    if not argv:
        _run_typer(argv)
        return

    # 4. Find first non-flag argument and check if it's a Typer command
    first_cmd = _find_first_command(argv)

    if first_cmd is None:
        # Only flags, no command → Typer handles global flags
        _run_typer(argv)
        return

    if first_cmd in _get_typer_commands():
        # Known Typer command → Typer
        _run_typer(argv)
    else:
        # Prompt, YAML file, or legacy invocation → legacy
        _run_legacy(argv)


if __name__ == "__main__":
    main()