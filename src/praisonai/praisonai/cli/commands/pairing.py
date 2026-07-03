"""Backward-compatibility shim for :mod:`praisonai.cli.commands.pairing`."""
import sys as _sys

from praisonai._bootstrap import ensure_praisonai_bot

ensure_praisonai_bot()
import praisonai_bot.cli.commands.pairing as _impl

_sys.modules[__name__] = _impl
