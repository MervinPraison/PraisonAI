"""
PraisonAI CLI Package

This package provides the command-line interface for PraisonAI.

Structure:
- main.py: Main CLI entry point (PraisonAI class)
- features/: Feature handlers for CLI flags and commands
"""

from .main import PraisonAI

__all__ = ["PraisonAI"]


def main():
    """CLI entry point function."""
    praison_ai = PraisonAI()
    praison_ai.main()
