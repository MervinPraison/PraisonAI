"""Standalone prompt dispatch without wrapper imports."""

from __future__ import annotations


def run_standalone_help() -> None:
    """Show minimal help when wrapper is not installed."""
    print("PraisonAI Code — standalone terminal agent runtime.")
    print("Install the full wrapper for YAML workflows: pip install praisonai")
