# __main__.py
"""
PraisonAI CLI Entry Point.

Supports both new Typer-based CLI and legacy argparse CLI.
"""

def main():
    """Main entry point with legacy support."""
    from .cli.legacy import main_with_legacy_support
    main_with_legacy_support()


if __name__ == "__main__":
    main()