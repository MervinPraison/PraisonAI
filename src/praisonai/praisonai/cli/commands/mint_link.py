"""Backward-compatibility shim for :mod:`praisonai.cli.commands.mint_link`."""
import sys as _sys

from praisonai._bootstrap import ensure_praisonai_bot

ensure_praisonai_bot()
import praisonai_bot.cli.commands.mint_link as _impl

_sys.modules[__name__] = _impl
