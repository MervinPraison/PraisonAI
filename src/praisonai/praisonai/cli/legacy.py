"""
Legacy compatibility shim for PraisonAI CLI.

Provides route_to_legacy() for dispatching to the original argparse-based
PraisonAI class. Used by __main__.py as a fallback for direct prompts,
YAML file paths, and deprecated --flag invocations.

This module no longer contains routing logic — all command dispatch is
handled by __main__.py using Typer auto-discovery.
"""

import sys


def route_to_legacy(argv):
    """
    Route to the legacy argparse CLI.

    Used for:
      - Direct prompts: praisonai "hello world"
      - YAML files:     praisonai agents.yaml
      - Legacy flags:   praisonai --llm gpt-4o --tools web_search "query"

    Returns:
        Exit code from legacy CLI
    """
    from praisonai.cli.main import PraisonAI

    original_argv = sys.argv
    sys.argv = ["praisonai"] + list(argv)

    try:
        praison = PraisonAI()
        result = praison.main()
        return 0 if result is None else (1 if result is False else 0)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0
    finally:
        sys.argv = original_argv


def main_with_legacy_support():
    """Entry point preserved for backward compatibility.

    Delegates to the new unified dispatcher in __main__.py.
    """
    from praisonai.__main__ import main
    main()


if __name__ == "__main__":
    main_with_legacy_support()
