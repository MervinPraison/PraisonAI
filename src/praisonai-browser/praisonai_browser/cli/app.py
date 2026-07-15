"""Typer CLI for standalone ``praisonai-browser``.

The browser command group is a single Typer app mounted as ``praisonai browser``
via ``_BROWSER_RESIDENT_COMMANDS`` in ``praisonai_code.cli.app``.
"""

from __future__ import annotations

from praisonai_browser.cli.commands.browser import app

__all__ = ["app"]
