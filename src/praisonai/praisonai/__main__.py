# __main__.py
"""
PraisonAI CLI — Unified Entry Point.

Single entry point for all CLI invocations.
Makes Typer the single dispatcher with narrow legacy shim for bare prompts/YAML.

Design:
  - Typer owns all command resolution
  - Legacy shim only for bare prompt/YAML invocations via Typer callback
  - Fail loud on registration errors - no silent degradation
"""

import sys


def _is_legacy_invocation(argv: list[str]) -> bool:
    """Check if this is a bare prompt or bare YAML invocation.
    
    Legacy invocations are:
    - Bare YAML file: "agents.yaml" 
    - Free-text prompt: "Create a weather app"
    
    All other invocations should be handled by Typer commands.
    """
    import os
    
    # Only the very first positional token is considered; option values never are.
    if not argv or argv[0].startswith("-"):
        return False
    
    first = argv[0]
    
    # Check for free-text prompt (contains spaces)
    if " " in first:
        return True
        
    # Check for YAML file that actually exists on disk
    if first.endswith((".yaml", ".yml")) and os.path.isfile(first):
        return True
        
    return False


def main():
    """Unified CLI entry point - Typer is the single dispatcher.

    Routing rules (in order):
      1. --version / -V    → print version and exit
      2. Legacy invocation → legacy shim (bare prompts/YAML only)
      3. Everything else   → Typer (owns all subcommands)
    """
    argv = sys.argv[1:]

    # 1. Quick version check (minimal imports)
    if "--version" in argv or "-V" in argv:
        from praisonai.version import __version__
        print(f"PraisonAI version {__version__}")
        return

    # 2. Check for legacy invocation (bare prompt/YAML)
    if _is_legacy_invocation(argv):
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
        return

    # 3. All other invocations → Typer (fail loud on registration errors)
    import os
    # Set up safer encoding for Windows legacy terminals
    if sys.platform == "win32" and hasattr(sys.stdout, 'encoding'):
        encoding = getattr(sys.stdout, 'encoding', '').lower()
        if encoding in ('cp1252', 'cp1251', 'cp850', 'ascii') or ('cp' in encoding and encoding != 'cp65001'):
            # Force UTF-8 mode for subprocess safety
            if 'PYTHONIOENCODING' not in os.environ:
                os.environ['PYTHONIOENCODING'] = 'utf-8'

    from praisonai.cli.app import app, register_commands
    
    # CRITICAL: Fail loud - do not swallow registration exceptions
    register_commands()  # Let any ImportError/other exceptions propagate
    
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


if __name__ == "__main__":
    main()