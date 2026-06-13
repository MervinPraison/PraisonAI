"""Backward-compatible entry point for PraisonAI CLI.

All command dispatch lives in __main__.py (Typer auto-discovery + legacy fallback).
This module is retained only for the main_with_legacy_support() console entry point.
"""


def main_with_legacy_support():
    """Entry point preserved for backward compatibility.

    Delegates to the new unified dispatcher in __main__.py.
    """
    from praisonai.__main__ import main
    main()


if __name__ == "__main__":
    main_with_legacy_support()
