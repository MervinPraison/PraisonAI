"""
PraisonAI CLI Package

This package provides the command-line interface for PraisonAI.

Structure:
- main.py: Main CLI entry point (PraisonAI class)
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
    from .main import PraisonAI
    praison_ai = PraisonAI()
    praison_ai.main()
