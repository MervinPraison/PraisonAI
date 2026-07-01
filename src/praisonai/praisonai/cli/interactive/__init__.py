"""Backward-compatibility shim: ``praisonai.cli.interactive`` moved to
``praisonai_code.cli.interactive``.

This module aliases the moved package so all existing imports such as
``from praisonai.cli.interactive.async_tui import AsyncTUI`` continue to work.
"""

from praisonai.cli._shim import alias_package as _alias_package

_alias_package(__name__, "praisonai_code.cli.interactive")
