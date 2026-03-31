"""
PraisonAI CLI Package

This package provides the command-line interface for PraisonAI.

Structure:
- ../.__main__.py: Unified CLI entry point (Typer-first, legacy fallback)
- app.py: Typer app with all command registrations
- main.py: Legacy argparse PraisonAI class (used for prompts/YAML)
- commands/: Individual Typer command modules
- features/: Feature handlers for CLI flags and commands
"""

__all__ = ["PraisonAI"]


def __getattr__(name):
    """Lazy load PraisonAI to avoid slow imports."""
    if name == "PraisonAI":
        from .main import PraisonAI
        return PraisonAI
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main():
    """CLI entry point function."""
    from praisonai.__main__ import main as _main
    _main()
